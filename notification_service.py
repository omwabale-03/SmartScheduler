import logging
from datetime import datetime, timedelta
from threading import Thread
from flask import render_template
from flask_mail import Message
from app import app, mail, db
from models import Reminder, Task, User, UserPreference

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self):
        logger.debug("Notification service initialized")
        
    
    def check_reminders(self):
        """
        Check for due reminders and send notifications.
        
        Returns:
            int: Number of reminders sent
        """
        # Find reminders that are due but haven't been sent
        now = datetime.now()
        due_reminders = Reminder.query.filter(
            Reminder.remind_at <= now,
            Reminder.sent == False
        ).all()
        
        sent_count = 0
        for reminder in due_reminders:
            success = self.send_reminder(reminder)
            if success:
                reminder.sent = True
                sent_count += 1
        
        db.session.commit()
        return sent_count
    
    def send_reminder(self, reminder):
        """
        Send a specific reminder notification.
        
        Args:
            reminder: The Reminder object
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            # Get the associated task
            task = Task.query.get(reminder.task_id)
            if not task:
                logger.error(f"Task not found for reminder {reminder.id}")
                return False
            
            # Get the user
            user = User.query.get(task.user_id)
            if not user:
                logger.error(f"User not found for task {task.id}")
                return False
            
            # Get user preferences
            user_pref = UserPreference.query.filter_by(user_id=user.id).first()
            
            # Check notification preferences
            notification_methods = ['email']  # Default
            if user_pref:
                notification_methods = user_pref.get_notification_preferences()
            
            # Send notifications based on preferences
            if 'email' in notification_methods:
                self.send_email_reminder(user, task)
            
            # For web notifications, we'll just mark it for display at next page load
            # This would be implemented on the front-end
            
            logger.debug(f"Sent reminder for task {task.id} to user {user.id}")
            return True
        except Exception as e:
            logger.error(f"Error sending reminder: {str(e)}")
            return False
    
    def send_email_reminder(self, user, task):
        """
        Send an email reminder for a task.
        
        Args:
            user: The User object
            task: The Task object
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            # Create email subject and body
            subject = f"Reminder: {task.title}"
            
            # Format times for display
            start_time_str = task.start_time.strftime("%I:%M %p") if task.start_time else "Not specified"
            
            # HTML message body
            html_body = f"""
            <h2>Task Reminder</h2>
            <p>Hello {user.username},</p>
            <p>This is a reminder for your task:</p>
            <div style="padding: 10px; border-left: 4px solid #007bff; background-color: #f8f9fa;">
                <h3>{task.title}</h3>
                <p>{task.description}</p>
                <p><strong>Start time:</strong> {start_time_str}</p>
                <p><strong>Priority:</strong> {task.priority}/5</p>
            </div>
            <p>Log in to your TimeMaster account to view more details or update this task.</p>
            <p>Best regards,<br>TimeMaster AI Assistant</p>
            """
            
            # Send email asynchronously
            thread = Thread(target=self._send_async_email, args=[user.email, subject, html_body])
            thread.start()
            
            return True
        except Exception as e:
            logger.error(f"Error creating email reminder: {str(e)}")
            return False
    
    def _send_async_email(self, recipient, subject, html_body):
        """
        Send email asynchronously.
        
        Args:
            recipient: Email recipient
            subject: Email subject
            html_body: HTML content
        """
        with app.app_context():
            try:
                msg = Message(
                    subject=subject,
                    recipients=[recipient],
                    html=html_body
                )
                mail.send(msg)
                logger.debug(f"Email sent to {recipient}")
            except Exception as e:
                logger.error(f"Error sending async email: {str(e)}")
    
    def send_daily_summary(self, user):
        """
        Send a daily summary of tasks to a user.
        
        Args:
            user: The User object
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            # Get today's tasks
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow = today + timedelta(days=1)
            
            today_tasks = Task.query.filter(
                Task.user_id == user.id,
                Task.due_date.between(today, tomorrow)
            ).order_by(Task.start_time).all()
            
            # Get upcoming tasks
            upcoming_tasks = Task.query.filter(
                Task.user_id == user.id,
                Task.due_date > tomorrow,
                Task.due_date <= tomorrow + timedelta(days=7),
                Task.status == 'pending'
            ).order_by(Task.due_date).all()
            
            # Create email subject and body
            subject = f"Your Daily Task Summary - {today.strftime('%A, %B %d')}"
            
            # HTML message body
            html_body = f"""
            <h2>Daily Task Summary</h2>
            <p>Hello {user.username},</p>
            <p>Here's your schedule for today:</p>
            """
            
            if today_tasks:
                html_body += "<h3>Today's Tasks</h3><ul>"
                for task in today_tasks:
                    time_str = task.start_time.strftime("%I:%M %p") if task.start_time else "Anytime"
                    status_style = "color: green;" if task.status == 'completed' else ""
                    html_body += f"<li style='{status_style}'><strong>{time_str}:</strong> {task.title}</li>"
                html_body += "</ul>"
            else:
                html_body += "<p>You have no tasks scheduled for today.</p>"
            
            if upcoming_tasks:
                html_body += "<h3>Upcoming Tasks</h3><ul>"
                for task in upcoming_tasks:
                    date_str = task.due_date.strftime("%A, %B %d")
                    html_body += f"<li><strong>{date_str}:</strong> {task.title}</li>"
                html_body += "</ul>"
            
            html_body += """
            <p>Log in to your TimeMaster account to view more details or update your tasks.</p>
            <p>Best regards,<br>TimeMaster AI Assistant</p>
            """
            
            # Send email asynchronously
            thread = Thread(target=self._send_async_email, args=[user.email, subject, html_body])
            thread.start()
            
            return True
        except Exception as e:
            logger.error(f"Error sending daily summary: {str(e)}")
            return False
