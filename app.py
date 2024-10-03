import datetime
import functools
import math
import os
import random
import re
import sys
import yaml

from langchain_community.chat_models           import ChatOpenAI
from langchain.prompts                         import ChatPromptTemplate
from langchain.output_parsers.openai_functions import JsonOutputFunctionsParser

from PyQt5.QtCore    import Qt
from PyQt5.QtGui     import QFont
from PyQt5.QtWidgets import QApplication, QComboBox, QGridLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QTabWidget, QTextEdit, QWidget

APP_VERSION          = '0.1.3'
APP_NAME             = 'Flashcard Pro'
APP_CARDS_PER_REVIEW = 20
APP_WRITING_WORDS    = 10
APP_BACKEND_LLM      = 'gpt-4o'
APP_STAGE_COLORS     = (
    '#DD0093',  # Apprentice
    '#882D9E',  # Guru
    '#294DDB',  # Master
    '#0093DD',  # Enlightened
    '#434343'   # Burned
)

class TabCardList(QWidget):
    SRS_STAGE_NAMES = ('Apprentice 1', 'Apprentice 2', 'Apprentice 3', 'Apprentice 4', 'Guru 1', 'Guru 2', 'Master', 'Enlightened', 'Burned')

    def card_add(self):
        english = self.input_english.text()
        target  = self.input_target.text()

        if english != '' and target != '' and not any([card['english'] == english and card['target'] == target for card in self.data['cards']]):
            self.data['cards'].append({
                'english': english,
                'target':  target,
            })

            self.card_add_ui(len(self.data['cards']) - 1)
            self.update()

    def card_add_ui(self, index):
        card = self.data['cards'][index]

        button_remove = QPushButton('Remove')
        button_remove.clicked.connect(functools.partial(self.card_remove, index))

        stage_name = TabCardList.SRS_STAGE_NAMES[card['stage']] if 'stage' in card else TabCardList.SRS_STAGE_NAMES[0]

        self.layout.addWidget(QLabel(card['english']), 3 + index, 1)
        self.layout.addWidget(QLabel(card['target']),  3 + index, 2)
        self.layout.addWidget(QLabel(stage_name),      3 + index, 3)
        self.layout.addWidget(button_remove,           3 + index, 4)

    def card_remove(self, index):
        self.data['cards'].pop(index)

        self.card_remove_ui(index)
        self.update()

    def card_remove_ui(self, index):  # Removes all cards starting from index.
        for row in range(index, len(self.data['cards'])):
            for column in range(1, 5):
                self.layout.itemAtPosition(3 + row, column).widget().deleteLater()

    def __init__(self):  # TODO: Allow modifications of existing words.
        super().__init__()

        try:
            with open('data.yaml', 'r') as file:
                self.data = yaml.safe_load(file)
        except FileNotFoundError:
            self.data = {'cards': []}

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        
        scroll_widget = QWidget()
        scroll_area.setWidget(scroll_widget)

        self.layout = QGridLayout(scroll_widget)

        self.layout.addWidget(QLabel('English'),         1, 1)
        self.layout.addWidget(QLabel('Target language'), 1, 2)
        self.layout.addWidget(QLabel('Current stage'),   1, 3)

        self.input_english = QLineEdit(self)
        self.input_target  = QLineEdit(self)
        self.button_add    = QPushButton('Add', self)

        self.layout.addWidget(self.input_english, 2, 1)
        self.layout.addWidget(self.input_target,  2, 2)
        self.layout.addWidget(self.button_add,    2, 4)

        self.button_add.clicked.connect(self.card_add)

        wrapping_layout = QGridLayout(self)
        wrapping_layout.addWidget(scroll_area)
        self.setLayout(wrapping_layout)
        
        self.update_ui()

    def update(self):
        self.update_ui()
        self.update_file()

    def update_ui(self):
        self.input_english.setText('')
        self.input_target.setText('')

        index_next = self.layout.rowCount() - 3

        while index_next < len(self.data['cards']):
            self.card_add_ui(index_next)

            index_next += 1

    def update_file(self):
        with open('data.yaml', 'w') as file:
            yaml.safe_dump(self.data, file, default_flow_style = False)

class TabCardReview(QWidget):
    SRS_WAIT_TIMES = (  # Taken from: https://knowledge.wanikani.com/wanikani/srs-stages/
        datetime.timedelta(hours =  4),  # Apprentice 1 -> Apprentice 2
        datetime.timedelta(hours =  8),  # Apprentice 2 -> Apprentice 3
        datetime.timedelta(days  =  1),  # Apprentice 3 -> Apprentice 4
        datetime.timedelta(days  =  2),  # Apprentice 4 -> Guru 1
        datetime.timedelta(weeks =  1),  # Guru 1       -> Guru 2
        datetime.timedelta(weeks =  2),  # Guru 2       -> Master
        datetime.timedelta(weeks =  4),  # Master       -> Enlightened
        datetime.timedelta(weeks = 16),  # Enlightened  -> Burned
    )

    def __init__(self):
        super().__init__()

        try:
            with open('data.yaml', 'r') as file:
                self.data = yaml.safe_load(file)
        except FileNotFoundError:
            self.data = {'cards': []}

        self.layout = QGridLayout(self)

        self.cards_per_stage = []

        for index in range(5):
            self.cards_per_stage.append(QLabel(''))
            self.cards_per_stage[index].setAlignment(Qt.AlignCenter)
            self.cards_per_stage[index].setStyleSheet(
                """QLabel {{
                    background-color: {color};
                    color:            white;
                    border-radius:    5px;
                    padding:          5px;
                    font-weight:      bold;
                    margin-top:       5px;
                    margin-bottom:    5px;
                }}""".format(color = APP_STAGE_COLORS[index]))

            self.layout.addWidget(self.cards_per_stage[index], 1, index + 1)

        self.cards_per_stage_update()

        self.to_review = self.cards_to_review()
        self.reviewing = []
        self.reviewed  = []

        self.info_status = QLabel('')
        self.info_card   = QLabel('')
        self.choice_dir  = QComboBox(self)

        for level in ('English → Target', 'Target → English', 'Both'):
            self.choice_dir.addItem(level)

        self.button_start = QPushButton('Start review')
        self.input_answer = QLineEdit(self)
        self.button_check = QPushButton('Check answer')
        self.button_next  = QPushButton('Next card')

        font_large = QFont()
        font_large.setPointSize(20)
        self.info_card.setFont(font_large)

        self.review_end()

        self.button_start.clicked.connect(self.review_start)
        self.button_check.clicked.connect(self.card_check)
        self.button_next.clicked.connect(self.card_next)

        self.layout.addWidget(self.info_status,  2, 1, 1, 5)
        self.layout.addWidget(self.info_card,    3, 1, 1, 5)
        self.layout.addWidget(self.choice_dir,   4, 1)
        self.layout.addWidget(self.button_start, 4, 2)
        self.layout.addWidget(self.input_answer, 4, 3)
        self.layout.addWidget(self.button_check, 4, 4)
        self.layout.addWidget(self.button_next,  4, 5)

    def cards_per_stage_update(self):
        cards_per_stage = [0] * (len(self.SRS_WAIT_TIMES) + 1)

        for card in self.data['cards']:
            if 'stage' not in card:
                card['stage']      = 1
                card['nextReview'] = datetime.datetime.now().replace(minute = 0, second = 0, microsecond = 0)

            cards_per_stage[card['stage']] += 1

        self.cards_per_stage[0].setText(f"{sum(cards_per_stage[ : 4])}\n\nApprentice")
        self.cards_per_stage[1].setText(f"{sum(cards_per_stage[4: 6])}\n\nGuru")
        self.cards_per_stage[2].setText(f"{    cards_per_stage[6] }\n\nMaster")
        self.cards_per_stage[3].setText(f"{    cards_per_stage[7] }\n\nEnlightened")
        self.cards_per_stage[4].setText(f"{    cards_per_stage[8] }\n\nBurned")

    def cards_to_review(self):
        cards_to_review = []

        for card in self.data['cards']:
            if 'stage' not in card:
                card['stage']      = 0
                card['nextReview'] = datetime.datetime.now()

            if card['nextReview'] is not None and card['nextReview'] <= datetime.datetime.now():
                cards_to_review.append(card)

        random.shuffle(cards_to_review)

        return cards_to_review

    def review_start(self):
        self.button_start.setEnabled(False)
        self.choice_dir.setEnabled(False)
        self.input_answer.setEnabled(True)
        self.button_check.setEnabled(True)
        self.button_next.setEnabled(False)

        while len(self.reviewing) < APP_CARDS_PER_REVIEW and len(self.to_review) > 0:
            card = self.to_review.pop(random.randint(0, len(self.to_review) - 1))

            card['lastReviewFailures'] = 0

            self.reviewing.append(card)
        
        self.card_next()

    def card_next(self):
        self.button_next.setEnabled(False)

        self.input_answer.setText('')

        if len(self.reviewing) == 0:
            self.input_answer.setEnabled(False)
            self.button_next.setEnabled(False)

            self.info_card.setText('')

            self.review_end()
        else:
            self.button_check.setEnabled(True)

            card = self.reviewing[0]

            self.info_status.setText(f"Cards in review: {len(self.reviewing)}, cards reviewed: {len(self.reviewed)}.")

            dir = random.randint(0, 1) if self.choice_dir.currentText() == 'Both' else self.choice_dir.currentIndex()

            if dir == 0:
                self.info_card.setText(f"{card['english']}\n\n")
            else:
                self.info_card.setText(f"{card['target']}\n\n")

            self.info_card.setStyleSheet('color: black;')

    @staticmethod
    def string_check(string_shown, string_input, card):
        # TODO #1: Look at other cards for extra options for the same word.
        # TODO #2: Split the string_input using / and check that each one matches something.
        string_target  = card['target'] if string_shown.strip() == card['english'] else card['english']
        strings_target = []

        for string_option in string_target.split('/'):
            strings_target.append(string_option.strip())
            strings_target.append(re.sub(r"\([^\)]+\)", '', string_option).strip())

        return any([string_input.lower() == string_target.lower() for string_target in strings_target])

    def card_check(self):
        if self.input_answer.text() == '':
            return

        self.button_check.setEnabled(False)
        self.button_next.setEnabled(True)

        card       = self.reviewing.pop(0)
        is_correct = TabCardReview.string_check(string_shown = self.info_card.text(), string_input = self.input_answer.text(), card = card)

        self.info_card.setText(f"{card['english']}\n\n{card['target']}")

        if is_correct:
            self.info_status.setText(f"Correct answer! Cards in review: {len(self.reviewing) + 1}, cards reviewed: {len(self.reviewed)}.")

            self.info_card.setStyleSheet('color: green;')

            self.reviewed.append(card)
        else:
            self.info_status.setText(f"Wrong answer! Cards in review: {len(self.reviewing) + 1}, cards reviewed: {len(self.reviewed)}.")

            self.info_card.setStyleSheet('color: red;')

            card['lastReviewFailures'] += 1

            self.reviewing.append(card)

    def review_end(self):  # Taken from: https://knowledge.wanikani.com/wanikani/srs-stages/
        for card in self.reviewed:
            if card['lastReviewFailures'] > 0:
                incorrect_adjustment_count = int(math.ceil(card['lastReviewFailures'] / 2.0))
                srs_penalty_factor         = 2 if card['stage'] >= 4 else 1

                card['stage']  = max(0, card['stage'] - incorrect_adjustment_count * srs_penalty_factor)
            else:
                card['stage'] += 1

            try:
                card['nextReview'] = (datetime.datetime.now() + self.SRS_WAIT_TIMES[card['stage']]).replace(minute = 0, second = 0, microsecond = 0)
            except IndexError:
                card['nextReview'] = None

        self.cards_per_stage_update()

        self.to_review = self.cards_to_review()
        self.reviewed  = []

        self.info_status.setText(f"You have {len(self.to_review)} cards to review.")

        can_review = len(self.to_review) > 0

        self.button_start.setEnabled(can_review)
        self.choice_dir.setEnabled(can_review)
        self.input_answer.setEnabled(False)
        self.info_card.setAlignment(Qt.AlignCenter)
        self.button_check.setEnabled(False)
        self.button_next.setEnabled(False)

        self.update_file()

    def update_file(self):
        with open('data.yaml', 'w') as file:
            yaml.safe_dump(self.data, file, default_flow_style = False)

class TabWriting(QWidget):
    def __init__(self):
        super().__init__()

        try:
            with open('data.yaml', 'r') as file:
                self.data = yaml.safe_load(file)
        except FileNotFoundError:
            self.data = {'cards': []}

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        
        scroll_widget = QWidget()
        scroll_area.setWidget(scroll_widget)

        self.layout = QGridLayout(scroll_widget)

        difficult_words = sorted(self.data['cards'], key = lambda card: card['lastReviewFailures'] if 'lastReviewFailures' in card else 0, reverse = True)
        self.word_list  = '\n'.join([f"∙ {card['target']} → {card['english']}" for card in difficult_words[: APP_WRITING_WORDS]])

        self.instructions = QLabel(f"Write a short text in the target language using the words listed below. You must use each word at least once.\n\n{self.word_list}")
        self.instructions.setWordWrap(True)

        self.layout.addWidget(self.instructions, 1, 1, 1, 4)

        self.input_text = QTextEdit('')

        self.layout.addWidget(self.input_text, 2, 1, 1, 4)

        level_label = QLabel('Level: ')
        level_label.setAlignment(Qt.AlignCenter)

        self.choice_level = QComboBox(self)

        for level in ('A1', 'A2', 'B1', 'B2', 'C1', 'C2'):
            self.choice_level.addItem(level)

        self.button_submit = QPushButton('Submit text')
        self.button_submit.clicked.connect(self.text_submit)

        self.info_score   = QLabel('Score: ? / 10')
        self.info_score.setAlignment(Qt.AlignCenter)

        self.layout.addWidget(level_label,        3, 1)
        self.layout.addWidget(self.choice_level,  3, 2)
        self.layout.addWidget(self.button_submit, 3, 3)
        self.layout.addWidget(self.info_score,    3, 4)

        self.info_feedback = QLabel('')
        self.info_feedback.setWordWrap(True)

        self.layout.addWidget(self.info_feedback, 4, 1, 1, 4)

        wrapping_layout = QGridLayout(self)
        wrapping_layout.addWidget(scroll_area) #, 0, 0, 1, 4)
        self.setLayout(wrapping_layout)

    def text_submit(self):
        self.input_text.setEnabled(False)
        self.choice_level.setEnabled(False)
        self.button_submit.setEnabled(False)

        QApplication.processEvents()

        functions = [{
            'name':        'evaluate_text',
            'description': 'Evaluates the text written by a student.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'feedback_words': {
                        'type':        'string',
                        'description': 'Your feedback for whether each word in the list was used at least once. Be verbose and provide concrete examples. Address the student directly.'
                    },
                    'score_words': {
                        'type':        'number',
                        'minimum':      0,
                        'maximum':     10,
                        'description': 'Your score for the "feedback_words" field. Be very strict in your evaluation, discounting points for each word that was not used.'
                    },
                    'feedback_spelling': {
                        'type':        'string',
                        'description': 'Your feedback for the spelling of words in the text. Be verbose and provide concrete examples. Address the student directly.'
                    },
                    'score_spelling': {
                        'type':        'number',
                        'minimum':      0,
                        'maximum':     10,
                        'description': 'Your score for the "feedback_spelling" field. Be very strict in your evaluation, discounting points for each spelling mistake.'
                    },
                    'feedback_grammar': {
                        'type':        'string',
                        'description': 'Your feedback for the grammar of the text. Be verbose and provide concrete examples. Your feedback should consider the level of the student. Address the student directly.'
                    },
                    'score_grammar': {
                        'type':        'number',
                        'minimum':      0,
                        'maximum':     10,
                        'description': 'Your score for the "feedback_grammar" field. Be very strict in your evaluation, discounting points for each grammar mistake.'
                    },
                    'feedback_semantic': {
                        'type':        'string',
                        'description': 'Your feedback for the semantics of the text: correct word usage, coherent text, etc. Be verbose and provide concrete examples. Your feedback should consider the level of the student. Address the student directly.'
                    },
                    'score_semantic': {
                        'type':        'number',
                        'minimum':      0,
                        'maximum':     10,
                        'description': 'Your score for the "feedback_semantic" field. Be very strict in your evaluation, discounting points for each semantic mistake.'
                    },
                    'feedback_final': {
                        'type':        'string',
                        'description': 'Your final feedback for the text. It should be a nicely-written summary of all other feedback fields, but you can also offer extra advice about how to improve. Your feedback should consider the level of the student. Address the student directly.'
                    },
                    'text_corrected': {
                        'type':        'string',
                        'description': 'Your corrected version of the student\'s text. It should be an HTML string, but you can only use the following tags: use <s></s> to strike out words that should be removed, and <b></b> to highlight words that should be added. Copy directly the parts that require no changes.'
                    }
                },
                'required': ['feedback_words', 'score_words', 'feedback_spelling', 'score_spelling', 'feedback_grammar', 'score_grammar', 'feedback_semantic', 'score_semantic', 'feedback_final', 'text_corrected']
            }
        }]

        prompt   = ChatPromptTemplate.from_messages((
            ('system', 'You are a language teacher with many decades of experience behind you. You are tasked with evaluating the writing of a student currently studying towards the {level} level in the CEFR, who was tasked with writing a short text in the target language using the words listed below. Each word had to be used at least once. Take a deep breath and let\'s think step by step. This task is very important to me!'),
            ('user', '### Word list:\n\n{word_list}'),
            ('user', '### Student\'s text:\n\n{input_text}')
        ))
        model    = ChatOpenAI(model_name = APP_BACKEND_LLM, temperature = 0.0).bind(function_call = {'name': 'evaluate_text'}, functions = functions)
        chain    = prompt | model | JsonOutputFunctionsParser()
        response = chain.invoke({
            'level':      self.choice_level.currentText(),
            'word_list':  self.word_list,
            'input_text': self.input_text.toPlainText(),
        })  # TODO: It still does not care about the level of the student; for the same text, scores should be lower as the level increases.

        score_final = min(response[key] for key in response if key.startswith('score_'))

        self.input_text.setHtml(response['text_corrected'])
        self.info_score.setText(f"Score: {score_final} / 10\n")
        self.info_feedback.setText(f"Feedback:\n\nWords: {response['feedback_words']} (score: {response['score_words']} / 10)\n\nSpelling: {response['feedback_spelling']} (score: {response['score_spelling']} / 10)\n\nGrammar: {response['feedback_grammar']} (score: {response['score_grammar']} / 10)\n\nSemantics: {response['feedback_semantic']} (score: {response['score_semantic']} / 10)\n\nSummary: {response['feedback_final']}")

class LanguageApp(QWidget):
    def __init__(self):
        super().__init__()

        assert 'OPENAI_API_KEY' in os.environ

        self.layout = QGridLayout(self)
        self.tabs   = QTabWidget(self)

        self.tabs.addTab(TabCardList(),   'Card list')
        self.tabs.addTab(TabCardReview(), 'Card review')
        self.tabs.addTab(TabWriting(),    'Writing')
        self.tabs.setCurrentIndex(1)

        self.layout.addWidget(self.tabs)

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setLayout(self.layout)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex  = LanguageApp()
    ex.show()

    sys.exit(app.exec_())