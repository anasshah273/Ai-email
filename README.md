# AI Email Spam and Phishing Classifier

A local university project that classifies an email subject and body as **Legitimate**, **Spam**, or **Phishing**. The Flask application uses a saved scikit-learn model, records successful analyses in SQLite, and provides a dashboard and searchable history page.

Predictions and confidence values are model estimates, not guarantees. Do not use this project as the sole basis for deciding whether a message is safe.

## Main features

- Responsive dashboard with database-backed totals, category percentages, and a distribution chart.
- Email subject/body analysis through the trained three-class classifier.
- Per-class probability estimates with an uncertainty notice.
- SQLite history with category filtering, subject search, pagination, record details, and confirmed deletion.
- Parameterized database queries and request validation.

## Technologies

Python, Flask, SQLite, scikit-learn, Pandas, NumPy, joblib, TF-IDF, Multinomial Naive Bayes, Logistic Regression, HTML, CSS, and JavaScript.

## Project structure

```text
AI_Email_Classifier/
├── app.py                         # Flask pages and JSON endpoints
├── database.py                    # SQLite initialization and queries
├── email_classifier.db            # Existing local analysis history
├── data/
│   ├── DATASET_INFO.md             # Source, counts, and license notes
│   ├── raw/                        # Original PhishFuzzer seed records
│   └── processed/                  # Audited/cleaned training data
├── ml/
│   ├── predict.py                  # Saved-model prediction
│   ├── text_processing.py          # Shared email text normalization
│   └── train_model.py              # Reproducible training/evaluation code
├── models/
│   ├── email_classifier.joblib     # Selected Logistic Regression model
│   └── tfidf_vectorizer.joblib     # Fitted TF-IDF vectorizer
├── reports/
│   ├── model_evaluation.json       # Detailed metrics and audit
│   └── model_evaluation.txt        # Readable evaluation summary
├── static/
│   ├── css/style.css
│   └── js/                         # Dashboard and history interactions
├── templates/                     # Flask-rendered dashboard/history pages
├── tests/test_app.py               # Automated Flask and model tests
├── tests/test_database.py          # SQLite helper unit tests
├── tests/test_predict_unit.py      # Prediction wrapper unit tests
├── tests/test_text_processing.py   # Text normalization unit tests
├── tests/performance_test.py       # Opt-in latency benchmark
└── requirements.txt
```

## Installation

The project has an existing Windows virtual environment at `.venv`. From PowerShell in the project folder, install the listed dependencies with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Python 3.10 or newer is recommended. SQLite is included with Python and needs no separate package.

## Run the application

From the project folder:

```powershell
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 5000
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) for the dashboard. The Email History page is available from the sidebar or at `/history`. The app creates the existing `email_classifier.db` and its history table if they do not exist; it does not create a second database.

The trained artifacts must be present at `models/email_classifier.joblib` and `models/tfidf_vectorizer.joblib`. They are included with this project. Training is not required to run the app.

## Run tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The unit tests check SQLite helpers, text normalization, and the prediction wrapper. The integration tests use an isolated temporary SQLite database and genuine held-out examples from the bundled dataset to check all three predictions, Flask routes, dashboard statistics, validation, and history filters/search/pagination/details/deletion. The project database is not used for destructive test operations.

### Performance benchmark

Run the opt-in benchmark separately (it is intentionally not part of the unit-test discovery command):

```powershell
.\.venv\Scripts\python.exe tests\performance_test.py --iterations 30
```

It reports median and p95 latency for saved-model inference and the in-process Flask `/predict` route including SQLite saving. It uses real held-out dataset rows and a temporary database. There is no fixed speed pass/fail threshold: timing depends on the computer and Python environment.

## Dataset and license limitations

Training uses the 3,300 original seed records from [DataPhish/PhishFuzzer](https://github.com/DataPhish/PhishFuzzer); the generated paraphrase variants are excluded. The source labels are `Valid`, `Spam`, and `Phishing`; `Valid` is mapped to `Legitimate`. After provenance filtering and duplicate removal, 3,223 records remain: 1,100 Legitimate, 1,005 Spam, and 1,118 Phishing.

The upstream repository states a **CC BY-NC 4.0** license for its repository and data, with attribution and non-commercial-use conditions; it also notes that emails from third-party sources remain subject to their original terms. Commercial use requires separate permission under the upstream terms. Read [the upstream license](https://github.com/DataPhish/PhishFuzzer/blob/main/LICENSE) and [dataset documentation](https://github.com/DataPhish/PhishFuzzer/blob/main/ReadME.md) before redistribution or other use. More detail is in [data/DATASET_INFO.md](data/DATASET_INFO.md).

## Machine-learning evaluation

The saved model was selected by **macro F1** using a leakage-aware grouped stratified split. TF-IDF was fit on the training partition only. The holdout contains 645 records, with zero `Original_ID` group overlap.

| Model | Accuracy | Macro precision | Macro recall | Macro F1 |
| --- | ---: | ---: | ---: | ---: |
| Multinomial Naive Bayes | 0.9085 | 0.9085 | 0.9069 | 0.9072 |
| Logistic Regression (selected) | 0.9209 | 0.9209 | 0.9196 | 0.9201 |

Selected-model confusion matrix (rows are actual labels; columns are predicted labels; order: Legitimate, Spam, Phishing):

```text
[[205, 10,  5],
 [ 12, 177, 12],
 [  7,  5, 212]]
```

The detailed report includes class-level precision, recall, F1, support, and both models' matrices in `reports/model_evaluation.txt` and `reports/model_evaluation.json`. Results describe this dataset split and are not a guarantee of performance on future mail.
