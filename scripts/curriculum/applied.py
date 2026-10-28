"""
The three applied streams: Data Science & ML, Cyber Security, and IoT.

IoT is here because KLS Tech Solutions builds IoT systems — it is the stream
where the briefs come from work the company has actually shipped, which is the
claim the whole platform rests on.

Cyber Security is written **defensively throughout**. Every task is about
finding and fixing a weakness in code the student controls, or in a target
explicitly provided for the purpose. Nothing here teaches attacking systems
belonging to other people, and the briefs say so in as many words.
"""

from app.services.chapter_pdf import (
    Chapter,
    bullets,
    code,
    h2,
    h3,
    key,
    note,
    p,
    steps,
    warn,
)
from scripts.curriculum import Stream, TaskSpec

# ===========================================================================
# Data Science & Machine Learning
# ===========================================================================

DATA_SCIENCE = Stream(
    slug="data-science-machine-learning",
    title="Data Science & Machine Learning",
    description=(
        "Work with real, messy data from end to end: clean it, understand it, "
        "model it, and say honestly how well the model works. The emphasis is "
        "on evaluation and on not fooling yourself, which is the part most "
        "courses skip and every employer cares about."
    ),
    duration="6 weeks",
    difficulty="intermediate",
    icon="chart",
    display_order=3,
    skills=["Python", "pandas", "NumPy", "scikit-learn", "Statistics", "Visualisation"],
    outcomes=[
        "Clean a messy dataset and document every decision you made",
        "Explore data and draw conclusions a sceptical reader would accept",
        "Train and evaluate a model without leaking information into it",
        "Explain a model's limitations as clearly as its accuracy",
    ],
    tasks=[
        TaskSpec(
            order_number=1,
            title="Clean a real dataset and defend your choices",
            description=(
                "Take a genuinely messy public dataset — inconsistent dates, "
                "missing values, duplicate rows, categories spelled four ways — "
                "and produce a clean version plus a written record of every "
                "decision.\n\n"
                "The cleaning is not the hard part. The hard part is that every "
                "choice you make changes the conclusions someone will later draw, "
                "so every choice needs a reason. 'Dropped 1,200 rows with a "
                "missing income' is a decision about who disappears from your "
                "analysis."
            ),
            requirements=[
                "A notebook that runs top to bottom on a fresh kernel",
                "Every missing-value decision stated with its reasoning",
                "Before and after row counts, with the loss accounted for",
                "Duplicate detection explained — what counts as the same record",
                "A short note on who or what is under-represented after cleaning",
            ],
            estimated_hours=12,
        ),
        TaskSpec(
            order_number=2,
            title="Exploratory analysis that answers a question",
            description=(
                "Start from a question worth asking of your cleaned dataset, "
                "then answer it with evidence. Not a gallery of charts — an "
                "argument.\n\n"
                "Each figure must earn its place by supporting a claim you "
                "state in words. We would rather see four charts that build a "
                "case than twenty that show you know matplotlib."
            ),
            requirements=[
                "A stated question in the first cell, before any analysis",
                "At least four figures, each with axis labels and a caption",
                "One finding that surprised you, and what you did to check it",
                "An explicit statement of what the data cannot tell you",
                "A conclusion a sceptical reader could follow without the code",
            ],
            estimated_hours=12,
        ),
        TaskSpec(
            order_number=3,
            title="A model, evaluated honestly",
            description=(
                "Train a model for a prediction task on your dataset and "
                "evaluate it properly. A simple baseline you understand beats a "
                "complex model you cannot explain.\n\n"
                "Start with the dumbest baseline — predicting the majority "
                "class, or the mean — and report it. A model that beats it by "
                "two points is a result; a model you never compared to it is "
                "not."
            ),
            requirements=[
                "A baseline reported before any real model",
                "Train/validation/test split made before any fitting or scaling",
                "The right metric for the problem, with the choice justified",
                "A confusion matrix or residual plot, read in words",
                "A section on where the model fails and who that would affect",
            ],
            estimated_hours=14,
        ),
    ],
    chapters=[
        Chapter(
            domain="Data Science & Machine Learning",
            number=1,
            title="Data Is Always Messier Than the Tutorial",
            level="Beginner",
            summary=(
                "Tutorials hand you a clean CSV. Real work hands you dates in "
                "four formats, a 'gender' column with eleven distinct values, "
                "and a note saying the 2023 export was different. This chapter "
                "is about that, because it is most of the job."
            ),
            minutes=35,
            outcomes=[
                "Load and inspect a dataset before touching it",
                "Decide what to do about missing values, with reasons",
                "Normalise inconsistent categories and dates",
                "Keep a record that makes your cleaning reproducible",
            ],
            blocks=[
                h2("Look before you clean"),
                p(
                    "The first thing to do with a new dataset is not to fix it. It is to "
                    "find out what it is: how many rows, what types, how much is "
                    "missing, and what the extremes look like. Five minutes here "
                    "prevents an afternoon of confusion later."
                ),
                code(
                    "import pandas as pd\n\n"
                    "df = pd.read_csv('responses.csv')\n\n"
                    "df.shape                      # rows, columns\n"
                    "df.info()                     # types and non-null counts\n"
                    "df.describe(include='all')    # ranges, and category counts\n"
                    "df.isna().mean().sort_values(ascending=False).head(10)",
                    "the first five minutes, every time",
                ),
                note(
                    "`df.isna().mean()` gives the *proportion* missing per column, which "
                    "is far more useful than the count. A column that is 94% empty is a "
                    "different problem from one that is 4% empty."
                ),
                h2("Missing data is information"),
                p(
                    "Why a value is missing matters more than that it is. A blank income "
                    "field because the question was optional is not the same as a blank "
                    "because the form crashed for one browser. The first is random-ish; "
                    "the second correlates with something and will bias everything you "
                    "do next."
                ),
                bullets(
                    "Drop the rows — fine when few are affected and nothing systematic "
                    "connects them. State how many you dropped.",
                    "Drop the column — reasonable past roughly half missing, because an "
                    "imputed majority is mostly invention.",
                    "Impute — median for skewed numbers, mode for categories, and add a "
                    "`was_missing` flag so the model can use the fact itself.",
                    "Leave it — some models handle nulls natively, and pretending you "
                    "know the value can be worse than admitting you do not.",
                ),
                code(
                    "# Impute, but keep the fact that it was missing.\n"
                    "df['income_missing'] = df['income'].isna()\n"
                    "df['income'] = df['income'].fillna(df['income'].median())",
                    "two lines, and no information destroyed",
                ),
                warn(
                    "Never impute using statistics from the whole dataset before "
                    "splitting into train and test. The median of the full set carries "
                    "information from the test rows into training, and your score comes "
                    "out better than the model is. This is leakage, and it is the most "
                    "common serious mistake in beginner projects."
                ),
                h2("Categories that are the same thing"),
                p(
                    "Free-text entry produces 'Bangalore', 'bangalore', 'Bengaluru', "
                    "'BLR' and 'Banglore'. Every one is a separate category to pandas, "
                    "and your counts are wrong in a way that looks plausible."
                ),
                code(
                    "df['city'].value_counts().head(30)   # look first\n\n"
                    "df['city'] = (df['city']\n"
                    "              .str.strip()\n"
                    "              .str.lower()\n"
                    "              .replace({'bengaluru': 'bangalore',\n"
                    "                        'blr': 'bangalore',\n"
                    "                        'banglore': 'bangalore'}))",
                    "normalise, then map the known variants",
                ),
                h3("Dates"),
                p(
                    "`01/02/2024` is January 2nd or February 1st depending on who typed "
                    "it. If a dataset mixes conventions there is no automatic fix, only a "
                    "decision you document. Parse explicitly and check what failed."
                ),
                code(
                    "df['joined'] = pd.to_datetime(df['joined'],\n"
                    "                              format='%Y-%m-%d',\n"
                    "                              errors='coerce')\n\n"
                    "# How many did not match the format you expected?\n"
                    "print(df['joined'].isna().sum())",
                    "coerce, then count the damage",
                ),
                key("Every cleaning decision changes who is in your dataset. Write them down as you go, not afterwards."),
                h2("Reproducibility"),
                p(
                    "A notebook you cleaned interactively, with cells run out of order "
                    "and some deleted, cannot be rerun by anyone including you next "
                    "month. Before you finish: restart the kernel and run every cell "
                    "from the top. If it fails, it was never real."
                ),
                steps(
                    "Keep the raw file untouched; write cleaned output to a new file.",
                    "Put the cleaning in functions, in order, in one place.",
                    "Restart and run all. Fix whatever breaks.",
                    "Record the row count at each stage so losses are visible.",
                ),
            ],
        ),
        Chapter(
            domain="Data Science & Machine Learning",
            number=2,
            title="Looking at Data Without Fooling Yourself",
            level="Intermediate",
            summary=(
                "Exploratory analysis is where you form beliefs, which makes it "
                "where you acquire wrong ones. This chapter is about the small "
                "set of habits that separate an analysis people trust from a "
                "folder of charts."
            ),
            minutes=40,
            outcomes=[
                "Choose a chart because of the question, not the aesthetic",
                "Read a distribution before summarising it",
                "Avoid the three mistakes that produce confident wrong answers",
                "Write a finding so a sceptical reader can check it",
            ],
            blocks=[
                h2("The mean is often a lie"),
                p(
                    "Summary statistics hide shape. Two datasets with identical means and "
                    "standard deviations can look nothing alike — one unimodal, one with "
                    "two clusters, one with an outlier dragging everything. Plot the "
                    "distribution before you quote a number from it."
                ),
                code(
                    "import matplotlib.pyplot as plt\n\n"
                    "fig, axes = plt.subplots(1, 2, figsize=(10, 4))\n"
                    "df['salary'].hist(bins=50, ax=axes[0])\n"
                    "df.boxplot(column='salary', by='city', ax=axes[1])\n"
                    "axes[0].set_xlabel('Salary (INR)')\n"
                    "axes[0].set_ylabel('Count')",
                    "shape first, summary second",
                ),
                p(
                    "For skewed data — income, response times, anything with a floor at "
                    "zero and a long tail — the median is almost always the honest "
                    "summary. A mean salary pulled upward by three founders describes "
                    "nobody in the dataset."
                ),
                h2("Choosing a chart"),
                bullets(
                    "One variable's shape — histogram.",
                    "Comparing groups — box plots side by side.",
                    "Two continuous variables — scatter, and add transparency when "
                    "points overlap.",
                    "Change over time — line, with time on the x-axis and a zeroed y-axis "
                    "unless you say otherwise.",
                    "Counts across categories — bar. Not a pie: people cannot compare "
                    "angles.",
                ),
                warn(
                    "A truncated y-axis makes a 2% difference look like a doubling. It is "
                    "sometimes legitimate, but it must be labelled. Doing it silently is "
                    "how honest analysts produce misleading charts."
                ),
                h2("Three ways to be confidently wrong"),
                h3("1 — Correlation read as cause"),
                p(
                    "Ice cream sales and drowning deaths correlate strongly. Neither "
                    "causes the other; summer causes both. In your own data the lurking "
                    "variable is usually something boring like 'which year' or 'which "
                    "team entered the record'."
                ),
                h3("2 — Survivorship"),
                p(
                    "If your dataset is customers who stayed, you cannot conclude "
                    "anything about why people leave. Ask what rows are missing from the "
                    "file entirely — that question has saved more analyses than any "
                    "technique."
                ),
                h3("3 — Simpson's paradox"),
                p(
                    "A trend present in every subgroup can reverse when the groups are "
                    "pooled, if the groups differ in size and base rate. The famous case "
                    "is a university whose admissions looked biased overall and were not "
                    "in a single department. Always check whether a headline result "
                    "survives being split by the obvious grouping variable."
                ),
                code(
                    "# Overall it looks like one thing...\n"
                    "df.groupby('treatment')['recovered'].mean()\n\n"
                    "# ...and within each severity level, the other.\n"
                    "df.groupby(['severity', 'treatment'])['recovered'].mean()",
                    "two lines that disagree",
                ),
                key("Before publishing a finding, split it by one variable you have not used yet. If it disappears, you have learned something important."),
                h2("Writing a finding"),
                p(
                    "A finding is a claim, the evidence for it, and its limits. All "
                    "three, in that order, in plain language."
                ),
                code(
                    "Students who read at least two chapters before their first\n"
                    "submission were approved on the first attempt 68% of the time,\n"
                    "against 41% for those who read none (n = 820, chart 3).\n\n"
                    "This is association, not effect. Students who read chapters are\n"
                    "plausibly more motivated in ways the data does not capture, and\n"
                    "nothing here was randomised.",
                    "claim, evidence, limit",
                ),
                note(
                    "The second paragraph is what makes the first one credible. An "
                    "analysis with no stated limitations reads as either naive or "
                    "selling something."
                ),
            ],
        ),
        Chapter(
            domain="Data Science & Machine Learning",
            number=3,
            title="Models, and Measuring Them Honestly",
            level="Advanced",
            summary=(
                "Fitting a model takes one line. Knowing whether to believe it "
                "takes the rest of this chapter. Most of the value is in the "
                "split, the baseline and the metric — all decided before "
                "training."
            ),
            minutes=45,
            outcomes=[
                "Split data so your score means something",
                "Pick a metric that matches the cost of being wrong",
                "Recognise leakage and overfitting from the numbers",
                "Describe where a model fails and who it fails",
            ],
            blocks=[
                h2("Split first. Everything else second."),
                p(
                    "Hold out a test set before you look at anything, and do not touch "
                    "it again until the end. Every decision you make after seeing test "
                    "data — a feature, a threshold, a model choice — leaks a little "
                    "information into it, and your final number stops being an estimate "
                    "of real performance."
                ),
                code(
                    "from sklearn.model_selection import train_test_split\n\n"
                    "X_train, X_test, y_train, y_test = train_test_split(\n"
                    "    X, y, test_size=0.2, random_state=42, stratify=y\n"
                    ")\n"
                    "# stratify keeps the class balance in both halves, which matters\n"
                    "# enormously when one class is rare.",
                    "the first modelling line you write",
                ),
                warn(
                    "If your rows are a time series, a random split is wrong: it trains "
                    "on the future to predict the past. Split by date instead, and never "
                    "shuffle."
                ),
                h2("Always have a baseline"),
                p(
                    "Before any model, measure the dumbest possible strategy. Predict the "
                    "majority class. Predict the mean. If your gradient-boosted ensemble "
                    "beats that by one point, you have learned that this problem is hard "
                    "or that your features are weak — which is worth knowing and is "
                    "invisible without the baseline."
                ),
                code(
                    "from sklearn.dummy import DummyClassifier\n\n"
                    "baseline = DummyClassifier(strategy='most_frequent')\n"
                    "baseline.fit(X_train, y_train)\n"
                    "print('baseline:', baseline.score(X_test, y_test))",
                    "report this number first, always",
                ),
                h2("Accuracy is usually the wrong metric"),
                p(
                    "If 2% of transactions are fraud, a model predicting 'not fraud' for "
                    "everything is 98% accurate and completely useless. The metric has to "
                    "reflect what being wrong costs, and the two ways of being wrong "
                    "rarely cost the same."
                ),
                bullets(
                    "Precision — of the cases I flagged, how many were real? Matters when "
                    "a false alarm is expensive.",
                    "Recall — of the real cases, how many did I catch? Matters when a "
                    "miss is expensive.",
                    "F1 — their harmonic mean, when you need one number and both matter.",
                    "ROC-AUC — ranking quality across all thresholds. Can look "
                    "reassuring on very imbalanced data; prefer precision-recall AUC "
                    "there.",
                ),
                p(
                    "Choose by asking what happens when the model is wrong. A cancer "
                    "screen wants recall — a false alarm costs another test, a miss costs "
                    "a life. A spam filter wants precision — a missed spam is an "
                    "annoyance, a legitimate email in the spam folder is a lost job "
                    "offer."
                ),
                code(
                    "from sklearn.metrics import classification_report, confusion_matrix\n\n"
                    "print(confusion_matrix(y_test, predictions))\n"
                    "print(classification_report(y_test, predictions))",
                    "read the matrix, not just the summary",
                ),
                h2("Leakage, the bug that looks like success"),
                p(
                    "Leakage is any information in your features that would not be "
                    "available at prediction time. The signature is a validation score "
                    "that is suspiciously good — 0.99 on a hard problem is not a "
                    "triumph, it is a message."
                ),
                bullets(
                    "A column computed after the outcome — `days_until_cancelled` when "
                    "predicting cancellation.",
                    "Scaling or imputing before the split, so test statistics reach the "
                    "training set.",
                    "An ID that happens to encode the answer because the file was sorted "
                    "by it.",
                    "The same customer in both train and test, when rows are not "
                    "independent.",
                ),
                code(
                    "from sklearn.pipeline import make_pipeline\n"
                    "from sklearn.preprocessing import StandardScaler\n"
                    "from sklearn.linear_model import LogisticRegression\n\n"
                    "# The pipeline fits the scaler inside each CV fold, on training\n"
                    "# data only. This is the structural fix for scaling leakage.\n"
                    "model = make_pipeline(StandardScaler(), LogisticRegression())",
                    "pipelines prevent a whole class of mistake",
                ),
                key("A score that surprises you upward deserves more scepticism than one that disappoints you."),
                h2("Overfitting, in two numbers"),
                p(
                    "Training score far above validation score means the model memorised "
                    "rather than generalised. Both scores low means it is too simple, or "
                    "the features do not carry the signal. You need both numbers to tell "
                    "these apart, which is why reporting only one is useless."
                ),
                h2("Write down where it fails"),
                p(
                    "Every model has a population it serves badly. Find it and say so: "
                    "split your errors by the obvious groups and look for the group where "
                    "the model is worst."
                ),
                code(
                    "errors = X_test.copy()\n"
                    "errors['wrong'] = predictions != y_test\n"
                    "errors.groupby('city')['wrong'].mean().sort_values(ascending=False)",
                    "three lines that often change the conclusion",
                ),
                note(
                    "If a model is markedly worse for an under-represented group, that is "
                    "a finding to report, not a rounding error. Task 3 asks for this "
                    "section explicitly."
                ),
            ],
        ),
    ],
)


# ===========================================================================
# Cyber Security  (defensive throughout)
# ===========================================================================

CYBER_SECURITY = Stream(
    slug="cyber-security",
    title="Cyber Security",
    description=(
        "Defensive security for people who build software. You will learn to "
        "find and fix the weaknesses that appear in real web applications, "
        "working only on code and targets you are explicitly authorised to "
        "test. The output of every task is a fix and a write-up, not an "
        "exploit."
    ),
    duration="6 weeks",
    difficulty="advanced",
    icon="shield",
    display_order=4,
    skills=[
        "Web security", "Threat modelling", "Secure coding",
        "Cryptography basics", "Code review", "Incident response",
    ],
    outcomes=[
        "Threat model a feature before it is built",
        "Find and fix the common classes of web vulnerability in your own code",
        "Review someone else's code for security problems",
        "Write a finding report an engineer can act on",
    ],
    tasks=[
        TaskSpec(
            order_number=1,
            title="Threat model a feature you are given",
            description=(
                "You are given the design of a password reset flow. Produce a "
                "threat model for it: what an attacker wants, how they might "
                "get it, and what you would change.\n\n"
                "No code and no tools — this is the thinking step, and doing it "
                "before building is what makes the rest cheap. Password reset "
                "is chosen deliberately: it is the feature most often got "
                "wrong, because it is an authentication bypass by design."
            ),
            requirements=[
                "A data flow diagram showing every trust boundary",
                "At least six threats, each with a realistic attacker goal",
                "A mitigation for each, with its cost honestly stated",
                "One threat you would accept rather than mitigate, and why",
                "A note on what your model does not cover",
            ],
            estimated_hours=10,
        ),
        TaskSpec(
            order_number=2,
            title="Find and fix five classes of flaw in a vulnerable app",
            description=(
                "You are given a deliberately vulnerable application — source "
                "code included, running locally on your own machine. Find the "
                "planted flaws, fix them, and prove the fixes work.\n\n"
                "**Scope is the application we provide, on your own machine, "
                "and nothing else.** Testing any system you do not own or have "
                "written authorisation for is a crime under the Information "
                "Technology Act, 2000, and ends the internship."
            ),
            requirements=[
                "At least five distinct vulnerability classes found and fixed",
                "Each finding: where, why it is exploitable, severity, and the fix",
                "A regression test per fix, failing before and passing after",
                "A diff of every change you made",
                "An explicit statement that you tested only the provided target",
            ],
            estimated_hours=16,
        ),
        TaskSpec(
            order_number=3,
            title="Harden an application and write the review",
            description=(
                "Take a small application you have written — one of your own "
                "projects, or your submission from another KLS stream — and "
                "perform a security review of it. Then fix what you find.\n\n"
                "The deliverable is a report an engineer who did not write the "
                "code could act on, plus the commits that address it. Reviewing "
                "your own work honestly is harder than it sounds and is most of "
                "what security engineers do."
            ),
            requirements=[
                "Review covering auth, access control, input handling, secrets and dependencies",
                "Findings rated by severity with the reasoning for each rating",
                "Dependency audit with any known vulnerable packages listed",
                "Security headers configured and verified",
                "Fixes committed, with before and after evidence",
            ],
            estimated_hours=14,
        ),
    ],
    chapters=[
        Chapter(
            domain="Cyber Security",
            number=1,
            title="Thinking Like a Defender",
            level="Beginner",
            summary=(
                "Security is not a feature you add at the end. It is a way of "
                "asking questions about a design — who is this for, what could "
                "go wrong, what would it cost — and the questions are cheap "
                "when asked early and very expensive when asked after launch."
            ),
            minutes=35,
            outcomes=[
                "Threat model a feature in under an hour",
                "Apply least privilege and defence in depth concretely",
                "Tell authentication, authorisation and accounting apart",
                "Work inside the legal and ethical boundaries of the field",
            ],
            blocks=[
                h2("The scope rule, first"),
                p(
                    "Everything in this stream is defensive. You will test software you "
                    "wrote, or software we explicitly provide for the purpose, running on "
                    "your own machine. Nothing else, ever."
                ),
                warn(
                    "Accessing a computer system without authorisation is an offence "
                    "under the Information Technology Act, 2000. 'I was only looking' is "
                    "not a defence, and neither is a bug bounty page you did not read "
                    "carefully. If you are not certain you are authorised, you are not "
                    "authorised."
                ),
                h2("Threat modelling, practically"),
                p(
                    "Four questions, asked of any feature. You can do this on a "
                    "whiteboard in forty minutes and it will find more real problems "
                    "than a scanner."
                ),
                steps(
                    "What are we building? Draw the data flow, and mark where data "
                    "crosses from something you control to something you do not.",
                    "What can go wrong? Walk the diagram and ask who would want to "
                    "interfere with each arrow.",
                    "What are we going to do about it? One mitigation per threat, with "
                    "its cost.",
                    "Did we do a good job? Revisit after building. The design changed "
                    "while you were building it; it always does.",
                ),
                p(
                    "STRIDE is a useful prompt for step two: Spoofing, Tampering, "
                    "Repudiation, Information disclosure, Denial of service, Elevation "
                    "of privilege. Walk each arrow and ask whether each applies."
                ),
                h3("A worked example: password reset"),
                bullets(
                    "Spoofing — can I request a reset for someone else's account and "
                    "receive the link?",
                    "Tampering — is the token predictable, or tied to nothing?",
                    "Information disclosure — does the response reveal whether an email "
                    "is registered?",
                    "Denial of service — can I send a thousand resets and exhaust the "
                    "mail quota, or flood someone's inbox?",
                    "Elevation of privilege — does the reset link log the user in, and "
                    "does it expire, and is it single use?",
                ),
                note(
                    "This platform answers those with: a random 32-byte token, a 30-minute "
                    "expiry, single use, an identical 204 response whether or not the "
                    "email exists, rate limiting per address and per IP, and a token "
                    "version bump that invalidates every existing session on reset."
                ),
                h2("Two principles that do most of the work"),
                h3("Least privilege"),
                p(
                    "Every component gets the minimum access needed for its job. The "
                    "database user your API connects as does not need DROP TABLE. The "
                    "service does not need to run as root. The API key for sending email "
                    "does not need permission to read the mailbox."
                ),
                h3("Defence in depth"),
                p(
                    "Assume each control will fail, because one of them will. Validate "
                    "on the client and the server. Check authorisation at the route and "
                    "in the query. Hash the password and rate limit the login and alert "
                    "on anomalies. Any single one of those failing should not be the "
                    "whole story."
                ),
                key("A control you have not tested is a control you do not have."),
                h2("Authentication, authorisation, accounting"),
                bullets(
                    "Authentication — who are you? Passwords, tokens, second factors.",
                    "Authorisation — may you do this? Roles, ownership checks.",
                    "Accounting — what did you do? Audit logs, which is how you answer "
                    "questions after an incident.",
                ),
                p(
                    "Most serious web vulnerabilities are authorisation failures, not "
                    "authentication failures. The attacker logs in perfectly legitimately "
                    "as themselves, then reaches something that was not theirs. Logging "
                    "in is the easy half to get right."
                ),
            ],
        ),
        Chapter(
            domain="Cyber Security",
            number=2,
            title="The Flaws That Actually Appear",
            level="Intermediate",
            summary=(
                "A small number of vulnerability classes account for most real "
                "breaches. This chapter covers them as a builder: what the flaw "
                "is, what it looks like in code, and the fix that makes it "
                "structurally impossible rather than merely unlikely."
            ),
            minutes=45,
            outcomes=[
                "Recognise broken access control in a code review",
                "Prevent injection by construction",
                "Understand XSS and the defences that work",
                "Handle secrets and dependencies responsibly",
            ],
            blocks=[
                h2("Broken access control"),
                p(
                    "The most common serious flaw, by a distance. The code checks that "
                    "you are logged in, then acts on an identifier from the request "
                    "without checking it belongs to you."
                ),
                code(
                    "# Vulnerable: authenticated, not authorised.\n"
                    "@app.get('/invoices/{invoice_id}')\n"
                    "def get_invoice(invoice_id: int, user = Depends(current_user)):\n"
                    "    return db.get(Invoice, invoice_id)\n\n"
                    "# Fixed: ownership is part of the query, not a separate check\n"
                    "# somebody can forget to write.\n"
                    "@app.get('/invoices/{invoice_id}')\n"
                    "def get_invoice(invoice_id: int, user = Depends(current_user)):\n"
                    "    invoice = db.scalar(select(Invoice).where(\n"
                    "        Invoice.id == invoice_id,\n"
                    "        Invoice.owner_id == user.id,\n"
                    "    ))\n"
                    "    if invoice is None:\n"
                    "        raise HTTPException(404)\n"
                    "    return invoice",
                    "the fix belongs in the query",
                ),
                p(
                    "Note the 404. Returning 403 confirms the invoice exists, which lets "
                    "an attacker enumerate valid IDs even though they cannot read them."
                ),
                h2("Injection"),
                p(
                    "Injection happens when data is concatenated into something that gets "
                    "interpreted — SQL, a shell command, an LDAP filter. The fix is never "
                    "escaping by hand; it is keeping data and instructions in separate "
                    "channels."
                ),
                code(
                    "# Vulnerable. An email of  ' OR '1'='1  returns every user.\n"
                    "db.execute(f\"SELECT * FROM users WHERE email = '{email}'\")\n\n"
                    "# Safe. The driver sends query and parameters separately, so no\n"
                    "# value can ever change the statement's meaning.\n"
                    "db.execute(text('SELECT * FROM users WHERE email = :email'),\n"
                    "           {'email': email})",
                    "parameterise, always",
                ),
                warn(
                    "An ORM is not automatic protection. `filter(text(f\"name = '{n}'\"))` "
                    "is just as injectable as raw SQL. The protection comes from "
                    "parameters, not from the library."
                ),
                h2("Cross-site scripting"),
                p(
                    "XSS is injection into a page: attacker-controlled text ends up "
                    "interpreted as script, and then runs with your origin's privileges — "
                    "reading the DOM, making authenticated requests, and reading any "
                    "token your JavaScript can reach."
                ),
                code(
                    "// Dangerous: the comment becomes markup.\n"
                    "element.innerHTML = comment;\n\n"
                    "// Safe: the comment stays text, whatever it contains.\n"
                    "element.textContent = comment;",
                    "React escapes by default — unless you opt out",
                ),
                bullets(
                    "In React, `dangerouslySetInnerHTML` is the opt-out. The name is the "
                    "warning; sanitise with a real library if you must use it.",
                    "A Content-Security-Policy header limits what an injection can do "
                    "even when one exists.",
                    "httpOnly cookies mean a successful XSS cannot steal the session "
                    "token, which turns a catastrophe into a serious bug.",
                ),
                h2("Secrets"),
                p(
                    "A secret in a repository is public the moment the repository is, and "
                    "deleting it in a later commit does not help — the history still has "
                    "it. Treat any committed secret as burned and rotate it."
                ),
                steps(
                    "Secrets come from the environment, never from source.",
                    "An example file lists every key with no real values.",
                    "A pre-commit secret scanner catches the mistake before it is made.",
                    "If one leaks: rotate first, then clean the history. In that order.",
                ),
                h2("Dependencies"),
                p(
                    "Most of the code you ship was written by strangers. That is normal "
                    "and fine, provided you know what you are shipping and can update it "
                    "quickly when something is found."
                ),
                code(
                    "pip-audit -r requirements.txt     # Python\n"
                    "npm audit --omit=dev              # JavaScript",
                    "run these in CI, read the output",
                ),
                note(
                    "Advisory rather than blocking is the right default in CI: a new CVE "
                    "in a transitive dependency should tell you about itself, not stop "
                    "you shipping an unrelated fix at 5pm."
                ),
                key("You cannot fix what you cannot inventory. Know your dependencies before you need to."),
            ],
        ),
        Chapter(
            domain="Cyber Security",
            number=3,
            title="Reviewing, Reporting and Responding",
            level="Advanced",
            summary=(
                "Finding a problem is half the work. The other half is "
                "explaining it so it gets fixed, rating it so the right thing "
                "gets fixed first, and knowing what to do on the day something "
                "has already gone wrong."
            ),
            minutes=40,
            outcomes=[
                "Review code for security with a repeatable method",
                "Rate a finding by severity defensibly",
                "Write a report an engineer can act on without you",
                "Follow an incident response sequence under pressure",
            ],
            blocks=[
                h2("A review method that finds things"),
                p(
                    "Reading a codebase front to back finds little. Follow the data "
                    "instead: start where untrusted input enters and trace it until it "
                    "reaches something that acts on it."
                ),
                steps(
                    "List the entry points: routes, forms, file uploads, webhooks, "
                    "query parameters, headers.",
                    "For each, find where that data is used — a query, a command, a "
                    "template, a redirect.",
                    "Ask what happens if it is hostile at that point.",
                    "Separately, list every privileged operation and check what guards "
                    "it.",
                ),
                p(
                    "The second list is where access control bugs live, and they are the "
                    "ones scanners miss. A scanner cannot know that this endpoint should "
                    "be admin-only; only someone who understands the product can."
                ),
                h2("Severity, defensibly"),
                p(
                    "Severity is impact multiplied by likelihood, and both need stating. "
                    "A critical-impact bug requiring physical access to a locked server "
                    "is not critical."
                ),
                bullets(
                    "Critical — unauthenticated access to other people's data, or remote "
                    "code execution. Fix today.",
                    "High — authenticated access to other people's data, or privilege "
                    "escalation. Fix this week.",
                    "Medium — needs unusual conditions, or impact is limited. Fix this "
                    "sprint.",
                    "Low — defence in depth, hardening, information disclosure of little "
                    "value. Backlog.",
                ),
                h2("A report that gets fixed"),
                p(
                    "Engineers fix what they can reproduce. A report that says 'the "
                    "login is insecure' gets argued with; one with a request, a response "
                    "and a line number gets fixed."
                ),
                code(
                    "TITLE     Any user can read any invoice\n"
                    "SEVERITY  High — authenticated, trivially exploitable\n"
                    "WHERE     app/api/invoices.py:42\n\n"
                    "DETAIL    The handler loads by ID from the path and never checks\n"
                    "          ownership. Signed in as user 7, requesting invoice 3\n"
                    "          (owned by user 2) returns it in full.\n\n"
                    "REPRO     1. Sign in as a normal user\n"
                    "          2. GET /api/invoices/3\n"
                    "          3. Observe another account's invoice in the response\n\n"
                    "IMPACT    Every invoice in the system is readable by any account.\n"
                    "          Names, addresses and amounts.\n\n"
                    "FIX       Scope the query by owner_id and return 404 when it\n"
                    "          matches nothing. Patch attached; test included.",
                    "the format we expect in task 3",
                ),
                note(
                    "Write the fix, not only the finding. A report that arrives with a "
                    "tested patch is acted on in an afternoon; one without may sit for a "
                    "quarter."
                ),
                h2("When it has already happened"),
                steps(
                    "Contain. Stop the bleeding — revoke the credentials, disable the "
                    "endpoint, take the feature offline. Availability is recoverable; "
                    "leaked data is not.",
                    "Preserve. Copy the logs somewhere safe before anything rotates them "
                    "away. You will want them in a week.",
                    "Assess. What was reachable, by whom, for how long? Resist the urge "
                    "to guess downward.",
                    "Notify. Affected users, and the regulator where the law requires "
                    "it. Under the DPDP Act that includes the Data Protection Board.",
                    "Fix and write it up. Blameless, specific, and shared.",
                ),
                warn(
                    "Do not quietly patch a breach that exposed personal data. In India "
                    "the DPDP Act 2023 creates notification duties, and quietly is "
                    "exactly how a manageable incident becomes a legal problem."
                ),
                key("The goal of a post-incident write-up is a system that cannot fail that way again, not a person who will not make that mistake again."),
            ],
        ),
    ],
)


# ===========================================================================
# IoT & Embedded Systems
# ===========================================================================

IOT = Stream(
    slug="iot-embedded-systems",
    title="IoT & Embedded Systems",
    description=(
        "Connected hardware, from the sensor to the dashboard. You will read "
        "real sensors on a microcontroller, get the readings to a server over "
        "an unreliable network, store them sensibly and show them to someone. "
        "The briefs come from the kind of systems KLS Tech Solutions builds."
    ),
    duration="8 weeks",
    difficulty="advanced",
    icon="cpu",
    display_order=5,
    skills=[
        "C/C++", "Python", "ESP32", "MQTT", "Sensors",
        "Time-series data", "Networking", "Power management",
    ],
    outcomes=[
        "Read sensors reliably and know when a reading is wrong",
        "Publish telemetry over MQTT and survive losing the network",
        "Store and query time-series data without it growing forever",
        "Reason about power, and about what happens when a device is offline",
    ],
    tasks=[
        TaskSpec(
            order_number=1,
            title="A sensor node that reports honestly",
            description=(
                "Build a device that reads at least two sensors and reports "
                "the readings over serial. An ESP32 or Arduino is fine, and a "
                "simulator is acceptable if you do not have hardware — say "
                "which you used.\n\n"
                "The real requirement is honesty about bad data. Sensors "
                "fail, disconnect and return nonsense. A node that reports "
                "-127°C as though it were a temperature is worse than one that "
                "reports nothing."
            ),
            requirements=[
                "At least two sensors, or one sensor and one derived value",
                "Readings validated against a plausible range before reporting",
                "A clear fault state when a sensor does not respond",
                "Non-blocking timing — no `delay()` in the main loop",
                "A wiring diagram or a photograph of the actual build",
            ],
            estimated_hours=14,
        ),
        TaskSpec(
            order_number=2,
            title="Get the data off the device and keep it",
            description=(
                "Publish your readings over MQTT to a broker, and write a "
                "subscriber that stores them. Then unplug the network and see "
                "what happens.\n\n"
                "The interesting half is the failure: Wi-Fi drops, the broker "
                "restarts, the device reboots mid-publish. A device that loses "
                "an hour of readings because the router rebooted is a device "
                "nobody will deploy."
            ),
            requirements=[
                "MQTT publish with a sensible topic structure, documented",
                "Reconnect with backoff — not a tight retry loop",
                "Readings buffered on the device while offline, then flushed",
                "A subscriber storing into a database with the device's timestamp",
                "Evidence of a disconnection test and what was recovered",
            ],
            estimated_hours=16,
        ),
        TaskSpec(
            order_number=3,
            title="A dashboard, and a device that lasts",
            description=(
                "Show the data: current values, history, and an alert when a "
                "reading leaves its expected range. Then measure your device's "
                "power draw and reduce it.\n\n"
                "Battery life is the constraint that decides whether an IoT "
                "product is viable. A node that must be charged weekly will not "
                "be deployed, however good the dashboard is."
            ),
            requirements=[
                "Dashboard showing live values and at least 24 hours of history",
                "A threshold alert that fires and is visible",
                "Measured current draw, before and after your optimisation",
                "Deep sleep or duty cycling implemented, with the trade-off stated",
                "An estimated battery life with the arithmetic shown",
            ],
            estimated_hours=16,
            require_live_demo=True,
        ),
    ],
    chapters=[
        Chapter(
            domain="IoT & Embedded Systems",
            number=1,
            title="Hardware Is Not a Computer",
            level="Beginner",
            summary=(
                "A microcontroller has kilobytes of RAM, no operating system "
                "to catch your mistakes, and nobody to restart it when it "
                "wedges. The habits that make embedded code work are different "
                "from the ones that make server code work, and this chapter is "
                "those habits."
            ),
            minutes=40,
            outcomes=[
                "Read digital and analog sensors and interpret the numbers",
                "Write a main loop that never blocks",
                "Detect a failed sensor instead of reporting its error value",
                "Debug a device that cannot print to a console",
            ],
            blocks=[
                h2("What you are working with"),
                p(
                    "An ESP32 has around 520 KB of RAM and a few megabytes of flash. "
                    "There is no process isolation, no virtual memory and no scheduler "
                    "unless you add one. A null pointer dereference does not raise an "
                    "exception — it reboots the device, usually with a stack trace in hex "
                    "that you will learn to read."
                ),
                bullets(
                    "Memory is finite and fragmentation is real. Avoid dynamic allocation "
                    "in the main loop.",
                    "`String` concatenation in a loop is the classic ESP32 heap killer. "
                    "Use fixed buffers.",
                    "The watchdog will reset you if you block too long. That is a "
                    "feature; do not disable it.",
                ),
                h2("Analog readings are not measurements"),
                p(
                    "An ADC gives you a number proportional to a voltage. Turning that "
                    "into a temperature requires knowing the reference voltage, the "
                    "resolution and the sensor's transfer function — and the result is "
                    "noisy."
                ),
                code(
                    "// 12-bit ADC, 0-4095, against a 3.3V reference.\n"
                    "int raw = analogRead(PIN);\n"
                    "float volts = raw * (3.3f / 4095.0f);\n"
                    "float celsius = (volts - 0.5f) * 100.0f;   // TMP36\n",
                    "three steps, each able to be wrong",
                ),
                p(
                    "Take several readings and use the median, not the mean. A single "
                    "electrical spike moves a mean and barely moves a median, and spikes "
                    "are what you get near a motor or a relay."
                ),
                h2("Never trust a reading you have not bounds-checked"),
                p(
                    "Every sensor has a failure value it returns when disconnected, and "
                    "usually that value is a plausible-looking number. A DS18B20 with a "
                    "loose data line reports -127°C quite happily."
                ),
                code(
                    "const float MIN_C = -40.0f;\n"
                    "const float MAX_C = 85.0f;\n\n"
                    "bool valid(float c) {\n"
                    "  // NaN fails every comparison, which catches it here too.\n"
                    "  return c >= MIN_C && c <= MAX_C;\n"
                    "}\n\n"
                    "if (!valid(celsius)) {\n"
                    "  publishFault(\"temp_sensor_out_of_range\");\n"
                    "  return;   // report the fault, not the number\n"
                    "}",
                    "the check that makes the data trustworthy",
                ),
                warn(
                    "A dashboard showing -127°C as a data point is worse than one showing "
                    "a gap, because somebody will average it. Task 1 is graded on this."
                ),
                h2("Never block the loop"),
                p(
                    "`delay(1000)` stops everything for a second — no network handling, "
                    "no button response, no watchdog feeding. Track time instead and act "
                    "when enough has passed."
                ),
                code(
                    "unsigned long lastRead = 0;\n"
                    "const unsigned long INTERVAL = 5000;\n\n"
                    "void loop() {\n"
                    "  unsigned long now = millis();\n"
                    "  // Subtraction, not comparison: this stays correct across the\n"
                    "  // ~49-day millis() rollover, where `now > last + I` does not.\n"
                    "  if (now - lastRead >= INTERVAL) {\n"
                    "    lastRead = now;\n"
                    "    readAndPublish();\n"
                    "  }\n"
                    "  mqtt.loop();   // still runs every pass\n"
                    "}",
                    "the standard non-blocking pattern",
                ),
                key("Every delay() in a connected device is time it is deaf to the network."),
                h2("Debugging without a debugger"),
                steps(
                    "Serial print, but sparingly — printing is slow and changes timing.",
                    "Blink an LED in a pattern for states you cannot print.",
                    "Log the reset reason on boot; it distinguishes a crash from a "
                    "watchdog from a power glitch.",
                    "When it only fails after six hours, log to flash and read it later.",
                ),
                note(
                    "'It works on the bench and fails in the field' is almost always "
                    "power, temperature or Wi-Fi signal. Check those three before "
                    "rewriting any code."
                ),
            ],
        ),
        Chapter(
            domain="IoT & Embedded Systems",
            number=2,
            title="Getting Data Off the Device",
            level="Intermediate",
            summary=(
                "The network will fail. Not might — will. This chapter is "
                "about MQTT, and about designing a device that treats "
                "disconnection as a normal condition rather than an error."
            ),
            minutes=40,
            outcomes=[
                "Publish and subscribe over MQTT with a sane topic design",
                "Choose a quality-of-service level deliberately",
                "Reconnect with backoff and buffer while offline",
                "Store telemetry so it stays queryable as it grows",
            ],
            blocks=[
                h2("Why MQTT rather than HTTP"),
                bullets(
                    "A persistent connection, so no TCP and TLS handshake per reading — "
                    "which is most of the energy cost of sending anything.",
                    "Tiny headers, measured in bytes, which matters on a metered SIM.",
                    "Publish/subscribe, so adding a second consumer needs no change on "
                    "the device.",
                    "Last Will and Testament: the broker announces your device's death "
                    "when it stops answering.",
                ),
                h2("Topic design"),
                p(
                    "Topics are a hierarchy and you should design it once, deliberately. "
                    "Retrofitting a topic structure means reflashing every device in the "
                    "field."
                ),
                code(
                    "kls/factory-1/line-2/press-07/telemetry/temperature\n"
                    "kls/factory-1/line-2/press-07/telemetry/vibration\n"
                    "kls/factory-1/line-2/press-07/status\n"
                    "kls/factory-1/line-2/press-07/command\n\n"
                    "# Subscribe to every temperature on the line:\n"
                    "#   kls/factory-1/line-2/+/telemetry/temperature\n"
                    "# Everything from one device:\n"
                    "#   kls/factory-1/line-2/press-07/#",
                    "general to specific, left to right",
                ),
                h3("Quality of service, chosen on purpose"),
                bullets(
                    "QoS 0 — fire and forget. Right for frequent readings where the next "
                    "one is along in five seconds.",
                    "QoS 1 — at least once. Duplicates possible, so the consumer must be "
                    "idempotent. The usual default.",
                    "QoS 2 — exactly once, four round trips. Rarely worth it; use it for "
                    "commands that must not repeat.",
                ),
                note(
                    "A door-unlock command is QoS 2. A temperature reading every five "
                    "seconds is QoS 0. Choosing QoS 2 for telemetry wastes power and "
                    "bandwidth to guarantee the delivery of a number that is about to be "
                    "superseded."
                ),
                h2("Reconnecting without making it worse"),
                p(
                    "When a broker goes down, every device reconnecting immediately and "
                    "continuously is a denial of service you built yourself. Back off "
                    "exponentially, and add jitter so your fleet does not retry in "
                    "lockstep."
                ),
                code(
                    "unsigned long backoff = 1000;          // start at 1s\n"
                    "const unsigned long MAX_BACKOFF = 60000;\n\n"
                    "void ensureConnected() {\n"
                    "  if (mqtt.connected()) { backoff = 1000; return; }\n"
                    "\n"
                    "  if (millis() - lastAttempt < backoff) return;\n"
                    "  lastAttempt = millis();\n"
                    "\n"
                    "  if (!mqtt.connect(deviceId, willTopic, 1, true, \"offline\")) {\n"
                    "    // Jitter stops the whole fleet retrying on the same tick.\n"
                    "    backoff = min(backoff * 2, MAX_BACKOFF) + random(0, 500);\n"
                    "  }\n"
                    "}",
                    "backoff, jitter, and a will message",
                ),
                h2("Buffer while offline"),
                p(
                    "A device that drops readings during a thirty-minute outage has a "
                    "thirty-minute hole in its history. Keep a ring buffer in RAM, and in "
                    "flash if the data matters, then flush it on reconnect."
                ),
                warn(
                    "Timestamp on the device, not on arrival. Otherwise an hour of "
                    "buffered readings all arrive with the same server timestamp and your "
                    "history is a vertical line. This is the single most common mistake "
                    "in buffered telemetry."
                ),
                code(
                    "{\n"
                    '  "device": "press-07",\n'
                    '  "ts": 1793020800,          // when it was READ\n'
                    '  "temp_c": 41.2,\n'
                    '  "buffered": true           // arrived late, and says so\n'
                    "}",
                    "the payload carries its own time",
                ),
                h2("Storing time-series"),
                p(
                    "Telemetry grows without limit and is almost always queried by time "
                    "range. A plain table works for a while; the thing that saves you is "
                    "deciding the retention policy before the table is large."
                ),
                bullets(
                    "Index on (device_id, ts) — the shape of nearly every query.",
                    "Downsample old data: per-second for a week, per-minute for a month, "
                    "hourly after that.",
                    "Partition by time so deleting old data is dropping a partition "
                    "rather than a DELETE that runs for an hour.",
                ),
                key("Decide how long you keep raw readings on day one. Retrofitting retention onto a billion-row table is a project."),
            ],
        ),
        Chapter(
            domain="IoT & Embedded Systems",
            number=3,
            title="Power, Reliability and the Field",
            level="Advanced",
            summary=(
                "A device on a bench is a prototype. A device on a pole, on a "
                "battery, in the rain, two hours away, is a product — and the "
                "difference is almost entirely power budget, update strategy "
                "and what happens when nobody is watching."
            ),
            minutes=40,
            outcomes=[
                "Build a power budget and estimate battery life",
                "Use deep sleep without losing the data you needed",
                "Design for remote updates safely",
                "Decide what a device does when it cannot reach anything",
            ],
            blocks=[
                h2("The power budget"),
                p(
                    "Battery life is arithmetic, and you can do it before building "
                    "anything. Average current draw against battery capacity, with a "
                    "derating for the fact that real batteries are worse than their "
                    "label."
                ),
                code(
                    "# A node waking for 2 seconds every 5 minutes.\n"
                    "#\n"
                    "#   awake:  160 mA for 2 s     -> 160 * (2/300)   = 1.07 mA avg\n"
                    "#   sleep:  0.01 mA for 298 s  -> 0.01 * (298/300) = 0.0099 mA\n"
                    "#   total average                                 ~ 1.08 mA\n"
                    "#\n"
                    "#   2000 mAh battery / 1.08 mA = ~1850 hours = ~77 days\n"
                    "#   derate 30% for temperature and ageing        = ~54 days\n",
                    "do this arithmetic before you build",
                ),
                p(
                    "Note what dominates: the two seconds awake, not the 298 asleep. "
                    "Halving the awake time nearly doubles the life. Reducing sleep "
                    "current from 0.01 mA to 0.005 mA changes almost nothing. Optimise "
                    "the term that matters."
                ),
                h2("Deep sleep, and what it costs"),
                p(
                    "Deep sleep cuts draw by three or four orders of magnitude. The "
                    "trade-off is that RAM is lost, the network connection is gone, and "
                    "waking costs both time and energy — Wi-Fi association is expensive, "
                    "which is why waking every ten seconds is worse than staying awake."
                ),
                code(
                    "// Survives deep sleep: stored in RTC memory, not RAM.\n"
                    "RTC_DATA_ATTR int bootCount = 0;\n\n"
                    "void setup() {\n"
                    "  bootCount++;\n"
                    "  readAndPublish();\n"
                    "  esp_sleep_enable_timer_wakeup(300ULL * 1000000ULL);\n"
                    "  esp_deep_sleep_start();   // setup() runs again on wake\n"
                    "}",
                    "there is no loop() in a sleeping device",
                ),
                note(
                    "A deep-sleeping device cannot receive a command — it is not "
                    "listening. If you need remote control, either stay connected, or "
                    "define a window after each wake when commands are collected. Decide "
                    "this before the hardware is deployed."
                ),
                h2("Updating devices you cannot reach"),
                p(
                    "Over-the-air update is the difference between a fixable product and "
                    "a recall. It is also the most dangerous code on the device, because "
                    "a bad update applied to a thousand nodes bricks a thousand nodes."
                ),
                steps(
                    "Verify a signature before writing anything. An unauthenticated OTA "
                    "endpoint is a remote code execution vulnerability with extra steps.",
                    "Write to a second partition; never overwrite the running firmware.",
                    "Boot the new image in trial mode and require it to confirm itself.",
                    "Roll back automatically if it does not — a device that cannot "
                    "report success must assume failure.",
                    "Stage the rollout: ten devices, then a hundred, then the fleet.",
                ),
                warn(
                    "Never ship an OTA that cannot roll back. The failure mode is "
                    "physically visiting every device, and for a pole-mounted sensor that "
                    "cost is larger than the device."
                ),
                h2("Behaviour when alone"),
                p(
                    "Define what the device does with no network, no server and no "
                    "instructions. This is a product decision, not a technical one, and "
                    "it should be written down."
                ),
                bullets(
                    "Keep measuring and buffering — almost always right.",
                    "Keep acting on the last known configuration, rather than reverting "
                    "to a default that might be unsafe.",
                    "Make the state visible locally: an LED that distinguishes 'working, "
                    "offline' from 'failed' saves a site visit.",
                    "Fail safe, not fail off. A valve controller losing contact should go "
                    "to the safe position, which is not always closed.",
                ),
                key("Write down the offline behaviour before you build it. If nobody decided it, the device still does something — just not deliberately."),
                h2("Before you call it finished"),
                steps(
                    "Run it for 72 hours uninterrupted and check for memory leaks and "
                    "drift.",
                    "Pull the network for an hour and confirm nothing was lost.",
                    "Pull the power mid-write and confirm it comes back cleanly.",
                    "Measure actual current draw rather than trusting the datasheet.",
                    "Hand it to someone else with only your README.",
                ),
            ],
        ),
    ],
)


STREAMS = [DATA_SCIENCE, CYBER_SECURITY, IOT]
