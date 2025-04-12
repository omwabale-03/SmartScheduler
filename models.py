from datetime import datetime
from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import json


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    tasks = db.relationship('Task', backref='user', lazy='dynamic')
    preferences = db.relationship('UserPreference', backref='user', uselist=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    priority = db.Column(db.Integer, default=0)  # 0-5, 5 being highest
    status = db.Column(db.String(20), default='pending')  # pending, completed, cancelled
    category = db.Column(db.String(50))
    ml_priority_score = db.Column(db.Float, default=0.0)  # ML-calculated priority
    calendar_event_id = db.Column(db.String(100))  # For Google Calendar sync
    
    # Relationships
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'priority': self.priority,
            'status': self.status,
            'category': self.category,
            'ml_priority_score': self.ml_priority_score,
            'calendar_event_id': self.calendar_event_id
        }


class UserPreference(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)
    working_hours_start = db.Column(db.Time, default=datetime.strptime('09:00', '%H:%M').time())
    working_hours_end = db.Column(db.Time, default=datetime.strptime('17:00', '%H:%M').time())
    break_duration = db.Column(db.Integer, default=30)  # in minutes
    productivity_peak_hours = db.Column(db.String(100), default=json.dumps(['09:00-12:00', '14:00-16:00']))
    preferred_task_duration = db.Column(db.Integer, default=60)  # in minutes
    calendar_connected = db.Column(db.Boolean, default=False)
    calendar_credentials = db.Column(db.Text)  # Stored securely
    notification_preferences = db.Column(db.String(100), default=json.dumps(['email', 'web']))
    
    def get_productivity_peak_hours(self):
        try:
            return json.loads(self.productivity_peak_hours)
        except:
            return []
    
    def set_productivity_peak_hours(self, hours_list):
        self.productivity_peak_hours = json.dumps(hours_list)
    
    def get_notification_preferences(self):
        try:
            return json.loads(self.notification_preferences)
        except:
            return ['email', 'web']
    
    def set_notification_preferences(self, preferences_list):
        self.notification_preferences = json.dumps(preferences_list)


class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    remind_at = db.Column(db.DateTime, nullable=False)
    sent = db.Column(db.Boolean, default=False)
    type = db.Column(db.String(20), default='email')  # email, notification
    
    # Relationship
    task = db.relationship('Task', backref='reminders')


class UserActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    activity_type = db.Column(db.String(50))
    details = db.Column(db.Text)
    
    # Relationship
    user = db.relationship('User', backref='activities')
