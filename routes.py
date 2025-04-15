import logging
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import render_template, request, redirect, url_for, flash, jsonify, session, abort
from flask_login import login_user, logout_user, login_required, current_user

from app import app, db, login_manager
from models import User, Task, UserPreference, UserActivity
from nlp_processor import NLPProcessor
from task_scheduler import TaskScheduler
from ml_prioritizer import MLPrioritizer
from calendar_integration import CalendarIntegration
from notification_service import NotificationService

# Initialize components
nlp_processor = NLPProcessor()
task_scheduler = TaskScheduler()
ml_prioritizer = MLPrioritizer()
calendar_integration = CalendarIntegration()
notification_service = NotificationService()

logger = logging.getLogger(__name__)

# Custom decorator for admin rights
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.id != 1:  # Simple example for admin check
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Check for due reminders every 5 minutes (would be handled by APScheduler in a real app)
@app.before_request
def check_reminders():
    if not request.endpoint:
        return
    
    # Only check on certain routes to avoid checking on every request
    if request.endpoint in ['static', 'login', 'register']:
        return
    
    # Check at most once every 5 minutes
    last_check = session.get('last_reminder_check', 0)
    now = datetime.now().timestamp()
    
    if now - last_check > 300:  # 5 minutes in seconds
        notification_service.check_reminders()
        session['last_reminder_check'] = now

# Record user activity
def record_activity(activity_type, details=None):
    if current_user.is_authenticated:
        activity = UserActivity(
            user_id=current_user.id,
            activity_type=activity_type,
            details=details
        )
        db.session.add(activity)
        db.session.commit()

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = 'remember' in request.form
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            record_activity('login')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if not username or not email or not password:
            flash('All fields are required', 'danger')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return render_template('register.html')
        
        # Create new user
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        
        # Create default user preferences
        preferences = UserPreference(user=user)
        db.session.add(preferences)
        
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    record_activity('logout')
    logout_user()
    return redirect(url_for('login'))

# Main routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    # Get today's tasks
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    today_tasks = Task.query.filter(
        Task.user_id == current_user.id,
        Task.due_date.between(today, tomorrow)
    ).order_by(Task.start_time).all()
    
    # Get upcoming tasks
    upcoming_tasks = Task.query.filter(
        Task.user_id == current_user.id,
        Task.due_date > tomorrow,
        Task.due_date <= tomorrow + timedelta(days=7),
        Task.status == 'pending'
    ).order_by(Task.due_date).all()
    
    # Get high priority tasks
    high_priority_tasks = Task.query.filter(
        Task.user_id == current_user.id,
        Task.status == 'pending',
        Task.priority >= 4
    ).order_by(Task.due_date).all()
    
    # Calculate completion stats
    completed_today = Task.query.filter(
        Task.user_id == current_user.id,
        Task.status == 'completed',
        Task.due_date.between(today, tomorrow)
    ).count()
    
    total_today = len(today_tasks)
    completion_rate = round((completed_today / total_today * 100) if total_today > 0 else 0)
    
    user_preferences = UserPreference.query.filter_by(user_id=current_user.id).first()
    
    # Get user activity
    recent_activity = UserActivity.query.filter_by(
        user_id=current_user.id
    ).order_by(UserActivity.timestamp.desc()).limit(5).all()
    
    # Add current date for the dashboard
    now = datetime.utcnow()
    
    return render_template(
        'dashboard.html',
        today_tasks=today_tasks,
        upcoming_tasks=upcoming_tasks,
        high_priority_tasks=high_priority_tasks,
        completion_rate=completion_rate,
        completed_today=completed_today,
        total_today=total_today,
        user_preferences=user_preferences,
        recent_activity=recent_activity,
        now=now
    )

@app.route('/tasks')
@login_required
def task_list():
    status_filter = request.args.get('status', 'pending')
    timeframe = request.args.get('timeframe', 'all')
    
    # Base query
    query = Task.query.filter_by(user_id=current_user.id)
    
    # Apply status filter
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    # Apply timeframe filter
    now = datetime.now()
    if timeframe == 'today':
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1) - timedelta(microseconds=1)
        query = query.filter(Task.due_date.between(start_of_day, end_of_day))
    elif timeframe == 'this_week':
        start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_week + timedelta(days=7) - timedelta(microseconds=1)
        query = query.filter(Task.due_date.between(start_of_week, end_of_week))
    elif timeframe == 'upcoming':
        query = query.filter(Task.due_date >= now)
    
    # Order by due date and priority
    tasks = query.order_by(Task.due_date, Task.priority.desc()).all()
    
    return render_template(
        'tasks.html',
        tasks=tasks,
        status_filter=status_filter,
        timeframe=timeframe
    )

@app.route('/tasks/create', methods=['GET', 'POST'])
@login_required
def create_task():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        due_date_str = request.form.get('due_date')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        priority = request.form.get('priority', 0, type=int)
        category = request.form.get('category')
        
        task_data = {
            'title': title,
            'description': description,
            'priority': priority,
            'category': category
        }
        
        # Parse dates
        if due_date_str:
            try:
                task_data['due_date'] = datetime.strptime(due_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Invalid due date format', 'danger')
                return render_template('create_task.html')
        
        # Parse times
        if start_time_str and due_date_str:
            try:
                time_parts = start_time_str.split(':')
                task_data['start_time'] = task_data['due_date'].replace(
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1])
                )
            except (ValueError, IndexError):
                flash('Invalid start time format', 'danger')
                return render_template('create_task.html')
        
        if end_time_str and due_date_str:
            try:
                time_parts = end_time_str.split(':')
                task_data['end_time'] = task_data['due_date'].replace(
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1])
                )
            except (ValueError, IndexError):
                flash('Invalid end time format', 'danger')
                return render_template('create_task.html')
        
        # Schedule the task
        task = task_scheduler.schedule_task(current_user, task_data)
        
        # Update ML priority score
        task.ml_priority_score = ml_prioritizer.prioritize_task(
            task, 
            Task.query.filter_by(user_id=current_user.id).all()
        )
        
        # Sync with Google Calendar if connected
        user_pref = UserPreference.query.filter_by(user_id=current_user.id).first()
        if user_pref and user_pref.calendar_connected and user_pref.calendar_credentials:
            event_id = calendar_integration.create_calendar_event(
                user_pref.calendar_credentials,
                task
            )
            if event_id:
                task.calendar_event_id = event_id
        
        db.session.commit()
        
        record_activity('create_task', f"{task.id}")
        flash('Task created successfully', 'success')
        return redirect(url_for('task_list'))
    
    return render_template('create_task.html')

@app.route('/tasks/<int:task_id>')
@login_required
def view_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    # Ensure user owns the task
    if task.user_id != current_user.id:
        abort(403)
    
    return render_template('view_task.html', task=task)

@app.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    # Ensure user owns the task
    if task.user_id != current_user.id:
        abort(403)
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        due_date_str = request.form.get('due_date')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        priority = request.form.get('priority', 0, type=int)
        category = request.form.get('category')
        status = request.form.get('status')
        
        task_data = {
            'title': title,
            'description': description,
            'priority': priority,
            'category': category,
            'status': status
        }
        
        # Parse dates
        if due_date_str:
            try:
                task_data['due_date'] = datetime.strptime(due_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Invalid due date format', 'danger')
                return render_template('edit_task.html', task=task)
        
        # Parse times
        if start_time_str and due_date_str:
            try:
                time_parts = start_time_str.split(':')
                task_data['start_time'] = task_data['due_date'].replace(
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1])
                )
            except (ValueError, IndexError):
                flash('Invalid start time format', 'danger')
                return render_template('edit_task.html', task=task)
        
        if end_time_str and due_date_str:
            try:
                time_parts = end_time_str.split(':')
                task_data['end_time'] = task_data['due_date'].replace(
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1])
                )
            except (ValueError, IndexError):
                flash('Invalid end time format', 'danger')
                return render_template('edit_task.html', task=task)
        
        # Update the task
        updated_task = task_scheduler.reschedule_task(task, task_data)
        
        # Update ML priority score
        updated_task.ml_priority_score = ml_prioritizer.prioritize_task(
            updated_task, 
            Task.query.filter_by(user_id=current_user.id).all()
        )
        
        # Sync with Google Calendar if connected
        user_pref = UserPreference.query.filter_by(user_id=current_user.id).first()
        if user_pref and user_pref.calendar_connected and user_pref.calendar_credentials:
            if updated_task.calendar_event_id:
                calendar_integration.update_calendar_event(
                    user_pref.calendar_credentials,
                    updated_task
                )
            else:
                event_id = calendar_integration.create_calendar_event(
                    user_pref.calendar_credentials,
                    updated_task
                )
                if event_id:
                    updated_task.calendar_event_id = event_id
        
        db.session.commit()
        
        record_activity('update_task', f"{task.id}")
        flash('Task updated successfully', 'success')
        return redirect(url_for('task_list'))
    
    return render_template('edit_task.html', task=task)

@app.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    # Ensure user owns the task
    if task.user_id != current_user.id:
        abort(403)
    
    # Delete associated calendar event if exists
    if task.calendar_event_id:
        user_pref = UserPreference.query.filter_by(user_id=current_user.id).first()
        if user_pref and user_pref.calendar_connected and user_pref.calendar_credentials:
            calendar_integration.delete_calendar_event(
                user_pref.calendar_credentials,
                task.calendar_event_id
            )
    
    # Record the activity before deleting
    record_activity('delete_task', f"{task.title}")
    
    # Delete the task
    db.session.delete(task)
    db.session.commit()
    
    flash('Task deleted successfully', 'success')
    return redirect(url_for('task_list'))

@app.route('/tasks/<int:task_id>/mark-complete', methods=['POST'])
@login_required
def mark_task_complete(task_id):
    task = Task.query.get_or_404(task_id)
    
    # Ensure user owns the task
    if task.user_id != current_user.id:
        abort(403)
    
    task.status = 'completed'
    db.session.commit()
    
    record_activity('task_completed', f"{task.id}")
    
    flash('Task marked as complete', 'success')
    return redirect(url_for('task_list'))

# AI Assistant routes
@app.route('/assistant')
@login_required
def assistant():
    return render_template('assistant.html')

@app.route('/api/assistant/process', methods=['POST'])
@login_required
def process_command():
    user_input = request.json.get('message', '')
    
    if not user_input:
        return jsonify({
            'success': False,
            'message': 'Please provide a message'
        })
    
    # Process the input using NLP
    command_data = nlp_processor.understand_command(user_input)
    
    response = {
        'success': True,
        'command_type': command_data['command_type'],
        'message': 'I understood your command'
    }
    
    # Handle different command types
    if command_data['command_type'] == 'create_task':
        task_data = command_data['data']
        
        # Schedule the task
        task = task_scheduler.schedule_task(current_user, task_data)
        
        # Update ML priority score
        task.ml_priority_score = ml_prioritizer.prioritize_task(
            task, 
            Task.query.filter_by(user_id=current_user.id).all()
        )
        
        # Sync with Google Calendar if connected
        user_pref = UserPreference.query.filter_by(user_id=current_user.id).first()
        if user_pref and user_pref.calendar_connected and user_pref.calendar_credentials:
            event_id = calendar_integration.create_calendar_event(
                user_pref.calendar_credentials,
                task
            )
            if event_id:
                task.calendar_event_id = event_id
        
        db.session.commit()
        
        record_activity('create_task_assistant', f"{task.id}")
        
        # Format response
        time_str = ''
        if task.start_time and task.end_time:
            start = task.start_time.strftime("%I:%M %p")
            end = task.end_time.strftime("%I:%M %p")
            time_str = f" from {start} to {end}"
        elif task.start_time:
            time_str = f" at {task.start_time.strftime('%I:%M %p')}"
        
        due_str = task.due_date.strftime("%A, %B %d") if task.due_date else ""
        
        response['message'] = f"I've scheduled \"{task.title}\"{time_str} on {due_str}."
        response['task'] = task.to_dict()
    
    elif command_data['command_type'] == 'list_tasks':
        # Get filter criteria
        timeframe = command_data['data'].get('timeframe', 'today')
        category = command_data['data'].get('category')
        priority = command_data['data'].get('priority')
        
        # Get tasks based on criteria
        tasks = task_scheduler.get_tasks_for_timeframe(current_user.id, timeframe)
        
        # Apply additional filters
        if category:
            tasks = [t for t in tasks if t.category and t.category.lower() == category.lower()]
        
        if priority == 'high':
            tasks = [t for t in tasks if t.priority >= 4]
        
        # Format response
        if tasks:
            task_count = len(tasks)
            timeframe_str = timeframe.replace('_', ' ')
            
            response['message'] = f"You have {task_count} tasks for {timeframe_str}:"
            response['tasks'] = [t.to_dict() for t in tasks]
        else:
            response['message'] = f"You don't have any tasks scheduled for {timeframe.replace('_', ' ')}."
            response['tasks'] = []
    
    elif command_data['command_type'] == 'update_task':
        task_title = command_data['data'].get('task_title')
        
        if not task_title:
            response['message'] = "I couldn't determine which task you want to update. Please specify the task title."
            return jsonify(response)
        
        # Find the task by title (using a simple fuzzy match)
        tasks = Task.query.filter_by(user_id=current_user.id).all()
        matching_task = None
        
        for task in tasks:
            if task_title.lower() in task.title.lower():
                matching_task = task
                break
        
        if not matching_task:
            response['message'] = f"I couldn't find a task with title containing '{task_title}'."
            return jsonify(response)
        
        # Update the task
        task_scheduler.reschedule_task(matching_task, command_data['data'])
        
        # Update ML priority score
        matching_task.ml_priority_score = ml_prioritizer.prioritize_task(
            matching_task, 
            Task.query.filter_by(user_id=current_user.id).all()
        )
        
        # Sync with Google Calendar if connected
        user_pref = UserPreference.query.filter_by(user_id=current_user.id).first()
        if user_pref and user_pref.calendar_connected and user_pref.calendar_credentials:
            if matching_task.calendar_event_id:
                calendar_integration.update_calendar_event(
                    user_pref.calendar_credentials,
                    matching_task
                )
        
        db.session.commit()
        
        record_activity('update_task_assistant', f"{matching_task.id}")
        
        response['message'] = f"I've updated the task \"{matching_task.title}\"."
        response['task'] = matching_task.to_dict()
    
    elif command_data['command_type'] == 'delete_task':
        task_title = command_data['data'].get('task_title')
        
        if not task_title:
            response['message'] = "I couldn't determine which task you want to delete. Please specify the task title."
            return jsonify(response)
        
        # Find the task by title (using a simple fuzzy match)
        tasks = Task.query.filter_by(user_id=current_user.id).all()
        matching_task = None
        
        for task in tasks:
            if task_title.lower() in task.title.lower():
                matching_task = task
                break
        
        if not matching_task:
            response['message'] = f"I couldn't find a task with title containing '{task_title}'."
            return jsonify(response)
        
        # Delete associated calendar event if exists
        if matching_task.calendar_event_id:
            user_pref = UserPreference.query.filter_by(user_id=current_user.id).first()
            if user_pref and user_pref.calendar_connected and user_pref.calendar_credentials:
                calendar_integration.delete_calendar_event(
                    user_pref.calendar_credentials,
                    matching_task.calendar_event_id
                )
        
        # Store task info before deletion
        task_info = matching_task.to_dict()
        
        # Delete the task
        db.session.delete(matching_task)
        db.session.commit()
        
        record_activity('delete_task_assistant', f"{task_title}")
        
        response['message'] = f"I've deleted the task \"{task_title}\"."
        response['deleted_task'] = task_info
    
    elif command_data['command_type'] == 'preferences':
        preference_type = command_data['data'].get('preference_type')
        
        # Get user preferences
        user_pref = UserPreference.query.filter_by(user_id=current_user.id).first()
        
        if not user_pref:
            user_pref = UserPreference(user_id=current_user.id)
            db.session.add(user_pref)
        
        # Update specific preferences
        if preference_type == 'working_hours':
            if 'start_time' in command_data['data']:
                start_time = command_data['data']['start_time']
                user_pref.working_hours_start = start_time.time()
            
            if 'end_time' in command_data['data']:
                end_time = command_data['data']['end_time']
                user_pref.working_hours_end = end_time.time()
            
            db.session.commit()
            
            start_str = user_pref.working_hours_start.strftime("%I:%M %p")
            end_str = user_pref.working_hours_end.strftime("%I:%M %p")
            
            response['message'] = f"I've updated your working hours to {start_str} - {end_str}."
        
        elif preference_type == 'breaks':
            if 'break_duration' in command_data['data']:
                user_pref.break_duration = command_data['data']['break_duration']
                db.session.commit()
                
                response['message'] = f"I've set your break duration to {user_pref.break_duration} minutes."
        
        elif preference_type == 'notifications':
            if 'notification_medium' in command_data['data']:
                medium = command_data['data']['notification_medium']
                prefs = user_pref.get_notification_preferences()
                
                if medium not in prefs:
                    prefs.append(medium)
                    user_pref.set_notification_preferences(prefs)
                    db.session.commit()
                
                response['message'] = f"I've updated your notification preferences to include {medium}."
        
        else:
            response['message'] = "I can help you set your working hours, break durations, and notification preferences. What would you like to change?"
    
    elif command_data['command_type'] == 'analytics':
        timeframe = command_data['data'].get('timeframe', 'all_time')
        
        # Get analytics data
        if timeframe == 'today':
            start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1) - timedelta(microseconds=1)
        elif timeframe == 'this_week':
            # Start of week (Monday)
            now = datetime.now()
            start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=7) - timedelta(microseconds=1)
        elif timeframe == 'this_month':
            now = datetime.now()
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # First day of next month - 1 microsecond
            if now.month == 12:
                end_date = datetime(now.year+1, 1, 1) - timedelta(microseconds=1)
            else:
                end_date = datetime(now.year, now.month+1, 1) - timedelta(microseconds=1)
        else:
            # All time
            start_date = datetime(2000, 1, 1)
            end_date = datetime.now()
        
        # Get tasks in timeframe
        tasks = Task.query.filter(
            Task.user_id == current_user.id,
            Task.created_at.between(start_date, end_date)
        ).all()
        
        completed_tasks = [t for t in tasks if t.status == 'completed']
        completion_rate = round((len(completed_tasks) / len(tasks) * 100) if tasks else 0)
        
        # Get average time to completion
        avg_completion_time = 0
        if completed_tasks:
            completion_times = []
            for task in completed_tasks:
                user_activity = UserActivity.query.filter_by(
                    user_id=current_user.id,
                    activity_type='task_completed',
                    details=str(task.id)
                ).first()
                
                if user_activity and task.created_at:
                    time_diff = (user_activity.timestamp - task.created_at).total_seconds() / 3600  # hours
                    completion_times.append(time_diff)
            
            if completion_times:
                avg_completion_time = round(sum(completion_times) / len(completion_times), 1)
        
        # Get completion by category
        categories = {}
        for task in tasks:
            if task.category:
                if task.category not in categories:
                    categories[task.category] = {'total': 0, 'completed': 0}
                
                categories[task.category]['total'] += 1
                if task.status == 'completed':
                    categories[task.category]['completed'] += 1
        
        # Format response
        timeframe_str = timeframe.replace('_', ' ')
        response['message'] = f"Here's your productivity report for {timeframe_str}:"
        response['analytics'] = {
            'total_tasks': len(tasks),
            'completed_tasks': len(completed_tasks),
            'completion_rate': completion_rate,
            'avg_completion_time_hours': avg_completion_time,
            'categories': categories
        }
    
    elif command_data['command_type'] == 'calendar_sync':
        # Get authorization URL for Google Calendar
        auth_url = calendar_integration.get_authorization_url(current_user.id)
        
        if auth_url:
            response['message'] = "To connect your Google Calendar, please click the link below:"
            response['auth_url'] = auth_url
        else:
            response['message'] = "I couldn't generate the Google Calendar authorization link. Please try again later."
    
    elif command_data['command_type'] == 'help':
        response['message'] = """
        I can help you manage your time more effectively! Here's what you can do:
        
        - Create tasks: "Schedule a meeting with John tomorrow at 2pm"
        - List tasks: "Show my tasks for today" or "What are my high priority tasks?"
        - Update tasks: "Reschedule my project review to Friday at 3pm"
        - Mark tasks complete: "Mark my dentist appointment as complete"
        - Delete tasks: "Delete my lunch meeting"
        - Get analytics: "How productive was I this week?"
        - Set preferences: "Change my working hours to 9am to 5pm"
        - Connect calendar: "Connect my Google Calendar"
        
        What would you like to do?
        """
    
    else:
        response['message'] = "I'm not sure what you're asking. You can create tasks, list tasks, update tasks, get analytics, or change your preferences. How can I help you?"
    
    return jsonify(response)

# Calendar integration routes
@app.route('/preferences')
@login_required
def preferences():
    user_pref = UserPreference.query.filter_by(user_id=current_user.id).first()
    
    if not user_pref:
        user_pref = UserPreference(user_id=current_user.id)
        db.session.add(user_pref)
        db.session.commit()
    
    return render_template('preferences.html', preferences=user_pref)

@app.route('/preferences/update', methods=['POST'])
@login_required
def update_preferences():
    user_pref = UserPreference.query.filter_by(user_id=current_user.id).first()
    
    if not user_pref:
        user_pref = UserPreference(user_id=current_user.id)
        db.session.add(user_pref)
    
    # Update working hours
    working_hours_start = request.form.get('working_hours_start')
    working_hours_end = request.form.get('working_hours_end')
    
    if working_hours_start:
        user_pref.working_hours_start = datetime.strptime(working_hours_start, '%H:%M').time()
    
    if working_hours_end:
        user_pref.working_hours_end = datetime.strptime(working_hours_end, '%H:%M').time()
    
    # Update break duration
    break_duration = request.form.get('break_duration', type=int)
    if break_duration:
        user_pref.break_duration = break_duration
    
    # Update productivity peak hours
    peak_hours = []
    for i in range(3):  # Allow up to 3 peak periods
        peak_start = request.form.get(f'peak_start_{i}')
        peak_end = request.form.get(f'peak_end_{i}')
        
        if peak_start and peak_end:
            peak_hours.append(f"{peak_start}-{peak_end}")
    
    if peak_hours:
        user_pref.set_productivity_peak_hours(peak_hours)
    
    # Update preferred task duration
    task_duration = request.form.get('preferred_task_duration', type=int)
    if task_duration:
        user_pref.preferred_task_duration = task_duration
    
    # Update notification preferences
    notification_prefs = []
    if 'email_notifications' in request.form:
        notification_prefs.append('email')
    if 'web_notifications' in request.form:
        notification_prefs.append('web')
    
    if notification_prefs:
        user_pref.set_notification_preferences(notification_prefs)
    
    db.session.commit()
    
    record_activity('update_preferences')
    flash('Preferences updated successfully', 'success')
    return redirect(url_for('preferences'))

@app.route('/calendar/authorize')
@login_required
def authorize_calendar():
    auth_url = calendar_integration.get_authorization_url(current_user.id)
    
    if auth_url:
        return redirect(auth_url)
    else:
        flash('Could not generate Google Calendar authorization URL', 'danger')
        return redirect(url_for('preferences'))

@app.route('/calendar/callback')
def calendar_callback():
    # Get state and authorization code
    state = request.args.get('state')
    code = request.args.get('code')
    
    # Verify state and get user ID
    if state != session.get('oauth_state'):
        flash('Invalid state parameter', 'danger')
        return redirect(url_for('preferences'))
    
    user_id = session.get('oauth_user_id')
    if not user_id:
        flash('User session expired', 'danger')
        return redirect(url_for('login'))
    
    # Handle the callback
    credentials_dict = calendar_integration.handle_oauth_callback(state, code)
    
    if not credentials_dict:
        flash('Failed to authorize Google Calendar', 'danger')
        return redirect(url_for('preferences'))
    
    # Store credentials in user preferences
    user_pref = UserPreference.query.filter_by(user_id=user_id).first()
    if not user_pref:
        user_pref = UserPreference(user_id=user_id)
        db.session.add(user_pref)
    
    user_pref.calendar_connected = True
    user_pref.calendar_credentials = json.dumps(credentials_dict)
    db.session.commit()
    
    record_activity('connect_calendar')
    flash('Google Calendar connected successfully', 'success')
    return redirect(url_for('preferences'))

@app.route('/calendar/disconnect', methods=['POST'])
@login_required
def disconnect_calendar():
    user_pref = UserPreference.query.filter_by(user_id=current_user.id).first()
    
    if user_pref:
        user_pref.calendar_connected = False
        user_pref.calendar_credentials = None
        db.session.commit()
        
        record_activity('disconnect_calendar')
        flash('Google Calendar disconnected', 'success')
    
    return redirect(url_for('preferences'))


@app.route('/optimize-schedule', methods=['POST'])
@login_required
def optimize_schedule():
    date_str = request.form.get('date')
    
    if date_str:
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format', 'danger')
            return redirect(url_for('dashboard'))
    else:
        date = datetime.now().date()
    
    tasks = task_scheduler.optimize_schedule(current_user.id, date)
    
    if tasks:
        record_activity('optimize_schedule', date_str)
        flash(f'Schedule optimized for {date}', 'success')
    else:
        flash('No tasks to optimize', 'info')
    
    return redirect(url_for('dashboard'))

@app.route('/update-priorities', methods=['POST'])
@login_required
def update_priorities():
    # Try to train ML model first
    model_trained = ml_prioritizer.train_model(current_user.id)
    
    # Update task priorities
    updated_count = ml_prioritizer.update_all_task_priorities(current_user.id)
    
    if model_trained:
        flash(f'ML model trained and {updated_count} task priorities updated', 'success')
    else:
        flash(f'{updated_count} task priorities updated using rule-based prioritization', 'info')
    
    record_activity('update_priorities')
    return redirect(url_for('dashboard'))

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500
