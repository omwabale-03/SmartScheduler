# SmartScheduler 🧠📅

SmartScheduler is an intelligent task management system powered by NLP and machine learning. It helps users schedule tasks smartly, prioritize efficiently, and integrate seamlessly with Google Calendar — all through a user-friendly web interface.

---

## 🚀 Features

- 🔐 User Authentication & Registration
- 📝 Create, Edit, Delete, and View Tasks
- 🧠 NLP-powered Task Understanding (spaCy)
- 🤖 ML-based Task Prioritization (RandomForest)
- 📅 Google Calendar Integration (OAuth2)
- 🔔 Smart Notifications for Deadlines
- 📊 Task Visualization with Charts
- 🌙 Dark Mode Support (custom CSS)
- 🧪 Error Handling with Custom 404/500 Pages

---

## 🛠️ Tech Stack

| Technology        | Purpose                              |
|------------------|--------------------------------------|
| **Flask**        | Web framework                        |
| **spaCy**        | Natural Language Processing          |
| **scikit-learn** | Machine Learning (Random Forest)     |
| **SQLite**       | Lightweight database                 |
| **HTML/CSS/JS**  | Frontend                             |
| **Google API**   | Calendar Integration (OAuth2)        |
| **Jinja2**       | Templating Engine                    |
| **Chart.js**     | Visualizing Task Data                |

---

## 🧠 How It Works

### NLP Processor
- Parses user inputs using `spaCy` to extract intent and context.

### Machine Learning Prioritizer
- Uses `RandomForestRegressor` to determine task priority based on due date, duration, and user preference history.

### Google Calendar Integration
- Uses OAuth 2.0 to connect and sync tasks with the user’s calendar.

---

## 🔧 Project Structure

```bash
SmartScheduler/
│
├── static/                  # CSS, JS, and static assets
│   ├── css/
│   └── js/
│
├── templates/               # HTML Templates (Jinja2)
│   ├── index.html
│   └── dashboard.html
│
├── app.py                   # Flask app entry point
├── main.py                  # Main runner
├── routes.py                # App routing
├── models.py                # SQLAlchemy models
├── nlp_processor.py         # spaCy-based NLP logic
├── ml_prioritizer.py        # ML Task prioritization
├── task_scheduler.py        # Core scheduling logic
├── calendar_integration.py  # Google Calendar API handling
├── notification_service.py  # Notifications & reminders
├── requirements.txt         # Python dependencies
└── README.md                # You are here
