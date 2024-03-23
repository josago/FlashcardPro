### Description

I developed *Flashcard Pro* when I started to study Indonesian and felt quite overwhelmed by the amount of vocabulary I kept forgetting. My main goal with this app was to implement the SRS method used in WaniKani (a website for learning Japanese kanji), because I felt it was intense but quite effective. When adding cards, I implemented a couple of extra, useful features:

* You can use the "/" character one or more times to specify alternatives for the card. That way, when you are prompted for it, writing any single one of the alternatives will be considered correct.
* Anything written within parenthesis will be considered optional, and can either be included in answers or not.

Cards are saved in a file called `data.yaml`, so be sure to back it up. The app also allows you to practice your weakest words by incorporating them into a short, free-format text. The app will then correct your text and give you a score for it; it does this by connecting to the OpenAI API in the background. To use this feature, you will need to set the `OPENAI_API_KEY` environment variable first.

This app has been tested to work in Python 3.10 and 3.11 and in both Linux and MacOS.

### Current limitations:

* Cards cannot be edited in the UI.
* The app does not support multiple decks of cards for multiple languages.

### Changelog:

#### 0.1.2:

* Initial GitHub release.