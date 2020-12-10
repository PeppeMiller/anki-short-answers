import base64
import difflib
import requests
from unicodedata import category

# import the main window object (mw) from aqt
from aqt import mw
# import the "show info" tool from utils.py
from aqt.utils import showInfo
# import all of the Qt GUI library
from aqt.qt import *
from aqt.sound import getAudio

from ._vendor.dragonmapper import hanzi


# Constants:
SETTINGS_ORGANIZATION = "rroessler"
SETTINGS_APPLICATION = "stt-anki-plugin"
API_KEY_SETTING_NAME = "google-stt-api-key"
FIELD_TO_READ_SETTING_NAME = "field-to-read"
FIELD_TO_READ_DEFAULT_NAME = "Front"


class IgnorableError(Exception):
    pass


def settings_dialog():
    SettingsDialog(app_settings, mw).show()


def test_pronunciation():
    api_key = app_settings.value(API_KEY_SETTING_NAME, "", type=str)
    field_to_read = app_settings.value(FIELD_TO_READ_SETTING_NAME, FIELD_TO_READ_DEFAULT_NAME, type=str)
    if api_key == '':
        settings_dialog()
        return
    if field_to_read not in mw.reviewer.card.note():
        error_dialog = QErrorMessage(mw)
        error_dialog.setWindowTitle("Check Pronunciation Addon")
        error_dialog.accept = lambda: custom_accept(error_dialog)
        error_dialog.showMessage(f'This plugin needs to know which field you are reading. '
                                 f'It\'s looking for a field named: "{field_to_read}", '
                                 f'but there is no field named: "{field_to_read}" on the current card. '
                                 f'Please check the settings.')
        return

    # TODO: rename stuff to be less Chinese specific
    hanzi = mw.reviewer.card.note()[field_to_read]
    hanzi = rstrip_punc(hanzi.strip()).strip()
    recorded_voice = getAudio(mw, False)
    try:
        tts_result = rest_request(recorded_voice, api_key)
        tts_result = rstrip_punc(tts_result.strip()).strip()
    except IgnorableError:
        return
    desired_pinyin = to_pinyin(hanzi)
    heard_pinyin = to_pinyin(tts_result)
    if desired_pinyin != heard_pinyin:
        # TODO: add window title
        showInfo("You were supposed to say:<br/>"
                 "{}<br/>"
                 "{}<br/>"
                 "But the computer heard you say:<br/>"
                 "{}<br/>"
                 "{}<br/>"
                 "<br/>"
                 "<span style=\"font-size:x-large\">{}</span><br/>".format(
            hanzi,
            desired_pinyin,
            tts_result,
            heard_pinyin,
            inline_diff(hanzi, tts_result)
        ), textFormat="rich")
    else:
        showInfo("Perfect. The computer heard you say:\n"
                 "{}\n"
                 "{}".format(
            tts_result,
            heard_pinyin
        ))


def rest_request(audio_file_path, api_key):
    with open(audio_file_path, 'rb') as audio_content:
        encoded_audio = base64.b64encode(audio_content.read())

    payload = {
        "config": {
            "encoding": "ENCODING_UNSPECIFIED",
            "sampleRateHertz": "44100",
            # TODO: allow language to be configurable
            "languageCode": "zh-TW"
        },
        "audio": {
            "content": encoded_audio.decode("utf8")
        }
    }

    r = requests.post("https://speech.googleapis.com/v1/speech:recognize?key={}".format(api_key), json=payload)
    try:
        r.raise_for_status()
    except requests.exceptions.HTTPError:
        if r.status_code == 400:
            error_dialog = QErrorMessage(mw)
            error_dialog.setWindowTitle("Check Pronunciation Addon")
            error_dialog.accept = lambda: custom_accept(error_dialog)
            error_dialog.showMessage('Received a 400 Error code; your API key is probably invalid.')
            raise IgnorableError
        # otherwise re-throw the exception
        raise
    data = r.json()
    if "results" not in data:
        error_dialog = QErrorMessage(mw)
        error_dialog.setWindowTitle("Check Pronunciation Addon")
        error_dialog.showMessage('No results from Speech-to-Text engine; maybe your audio recording was silent or empty?')
        raise IgnorableError
    transcript = ""
    for result in data["results"]:
        transcript += result["alternatives"][0]["transcript"].strip() + " "
    return transcript


def custom_accept(self: QErrorMessage):
    QErrorMessage.accept(self)
    settings_dialog()


def inline_diff(a, b):
    matcher = difflib.SequenceMatcher(None, a, b)

    def process_tag(tag, i1, i2, j1, j2):
        if tag == 'equal':
            return to_pinyin(matcher.a[i1:i2])
        elif tag == 'replace':
            color = "red"
            seq = matcher.b[j1:j2]
        elif tag == 'delete':
            color = "orange"
            seq = matcher.a[i1:i2]
        elif tag == 'insert':
            color = "red"
            seq = matcher.b[j1:j2]
        else:
            assert False, f"Unknown tag {tag}"
        return f"<span style=\"color:{color}\">{to_pinyin(seq)}</span>"

    return ''.join(process_tag(*t) for t in matcher.get_opcodes())


def to_pinyin(sent):
    return hanzi.to_pinyin(sent, accented=False)


def rstrip_punc(s):
    """ Strips all rightmost punctuation, based on Unicode characters. """
    ei = len(s)
    # The startswith('P') indicates punctuation
    while ei > 0 and category(s[ei - 1]).startswith('P'):
        ei -= 1
    return s[:ei]


class SettingsDialog(QDialog):

    def __init__(self, my_settings: QSettings, *args, **kwargs):
        super(SettingsDialog, self).__init__(*args, **kwargs)
        self.setWindowTitle("Settings")
        self.my_settings = my_settings

        buttons = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

        self.buttonBox = QDialogButtonBox(buttons)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.api_key_textbox = QLineEdit()
        self.api_key_textbox.setText(self.my_settings.value(API_KEY_SETTING_NAME, "", type=str))
        api_setting_label = QLabel("API Key:")

        self.field_to_read_textbox = QLineEdit()
        self.field_to_read_textbox.setText(self.my_settings.value(FIELD_TO_READ_SETTING_NAME, FIELD_TO_READ_DEFAULT_NAME, type=str))
        field_to_read_setting_label = QLabel("Name of Card Field to Read:")

        api_hor = QHBoxLayout()
        api_hor.addWidget(field_to_read_setting_label)
        api_hor.addWidget(self.field_to_read_textbox)

        ftr_hor = QHBoxLayout()
        ftr_hor.addWidget(api_setting_label)
        ftr_hor.addWidget(self.api_key_textbox)

        self.layout = QVBoxLayout()
        self.layout.addLayout(api_hor)
        self.layout.addLayout(ftr_hor)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

    def accept(self):
        self.my_settings.setValue(API_KEY_SETTING_NAME, self.api_key_textbox.text())
        self.my_settings.setValue(FIELD_TO_READ_SETTING_NAME, self.field_to_read_textbox.text())
        super(SettingsDialog, self).accept()

    def reject(self):
        super(SettingsDialog, self).reject()


app_settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)

cp_action = QAction("Check Pronunciation", mw)
cp_action.triggered.connect(test_pronunciation)
mw.form.menuTools.addAction(cp_action)

cps_action = QAction("Check Pronunciation Settings", mw)
cps_action.triggered.connect(settings_dialog)
mw.form.menuTools.addAction(cps_action)
