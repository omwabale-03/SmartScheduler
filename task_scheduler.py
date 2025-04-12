import logging
from datetime import datetime, timedelta
from models import Task, UserPreference, Reminder
from app import db
import json

logger = logging.getLogger(__name__)

class TaskScheduler:
    def __init__(self):
        logger.debug("Task scheduler initialized")
    
    def schedule_task(self, user, task_data):
        """
        Schedule a task based on the provided data and user preferences.
        
        Args:
            user: The user object
            task_data: Dictionary with task details
            
        Returns:
            task: The created Task object
        """
        # Create a new task
        task = Task(
            title=task_data.get('title', 'Untitled Task'),
            description=task_data.get('description', ''),
            user_id=user.id,
            due_date=task_data.get('due_date'),
            start_time=task_data.get('start_time'),
            end_time=task_data.get('end_time'),
            priority=task_data.get('priority', 0),
            category=task_data.get('category')
        )
        
        # If no due date is specified, set it based on other parameters
        if not task.due_date:
            if task.start_time:
                # If start time is specified, use that day as due date
                task.due_date = task.start_time.replace(hour=23, minute=59, second=59)
            else:
                # Default to today
                task.due_date = datetime.now().replace(hour=23, minute=59, second=59)
        
        # If we have a duration but no end time, calculate end time
        if not task.end_time and task.start_time and task_data.get('duration'):
            task.end_time = task.start_time + timedelta(minutes=task_data.get('duration'))
        
        # If no times are specified but we have a due date, 
        # use user preferences to suggest a time
        if not task.start_time and task.due_date:
            user_prefs = UserPreference.query.filter_by(user_id=user.id).first()
            if user_prefs:
                # Get user's preferred working hours
                working_start = user_prefs.working_hours_start
                working_end = user_prefs.working_hours_end
                
                # Try to find an open slot based on productivity peak hours
                peak_hours = user_prefs.get_productivity_peak_hours()
                if peak_hours:
                    # Use first peak hour period as default
                    try:
                        peak_start, peak_end = peak_hours[0].split('-')
                        peak_start_hour, peak_start_min = map(int, peak_start.split(':'))
                        peak_end_hour, peak_end_min = map(int, peak_end.split(':'))
                        
                        task_start = task.due_date.replace(
                            hour=peak_start_hour, 
                            minute=peak_start_min,
                            second=0
                        )
                        
                        # If this is in the past, move to next available day
                        if task_start < datetime.now():
                            task_start = datetime.now() + timedelta(hours=1)
                            task_start = task_start.replace(
                                hour=peak_start_hour,
                                minute=peak_start_min,
                                second=0
                            )
                            if task_start.hour > peak_end_hour or (task_start.hour == peak_end_hour and task_start.minute >= peak_end_min):
                                # Move to the next day
                                task_start = task_start + timedelta(days=1)
                        
                        task.start_time = task_start
                                                
                        # Set end time based on preferred task duration
                        task_duration = user_prefs.preferred_task_duration
                        task.end_time = task.start_time + timedelta(minutes=task_duration)
                        
                        # Ensure end time doesn't exceed peak period
                        peak_end_time = task.due_date.replace(
                            hour=peak_end_hour,
                            minute=peak_end_min,
                            second=0
                        )
                        if task.end_time > peak_end_time:
                            task.end_time = peak_end_time
                    except:
                        # If any error occurs in parsing peak hours, fallback to default
                        task.start_time = task.due_date.replace(
                            hour=working_start.hour,
                            minute=working_start.minute,
                            second=0
                        )
                        task.end_time = task.start_time + timedelta(minutes=user_prefs.preferred_task_duration)
                else:
                    # No peak hours, use beginning of working day
                    task.start_time = task.due_date.replace(
                        hour=working_start.hour,
                        minute=working_start.minute,
                        second=0
                    )
                    task.end_time = task.start_time + timedelta(minutes=user_prefs.preferred_task_duration)
        
        # Add to database
        db.session.add(task)
        db.session.commit()
        
        # Create reminder for the task
        self.create_reminder(task, user)
        
        return task
    
    def reschedule_task(self, task, new_data):
        """
        Reschedule an existing task with new timing data.
        
        Args:
            task: The Task object to reschedule
            new_data: Dictionary with updated task details
            
        Returns:
            task: The updated Task object
        """
        # Update the task with new data
        if 'due_date' in new_data:
            task.due_date = new_data['due_date']
        if 'start_time' in new_data:
            task.start_time = new_data['start_time']
        if 'end_time' in new_data:
            task.end_time = new_data['end_time']
        if 'priority' in new_data:
            task.priority = new_data['priority']
        if 'status' in new_data:
            task.status = new_data['status']
        if 'category' in new_data:
            task.category = new_data['category']
        if 'title' in new_data:
            task.title = new_data['title']
        if 'description' in new_data:
            task.description = new_data['description']
        
        # If we have a duration but no end time, calculate end time
        if 'duration' in new_data and task.start_time and not task.end_time:
            task.end_time = task.start_time + timedelta(minutes=new_data['duration'])
        
        # Update database
        db.session.commit()
        
        # Update reminders for the task
        self.update_reminders(task)
        
        return task
    
    def optimize_schedule(self, user_id, date=None):
        """
        Optimize the user's schedule for the given date.
        
        Args:
            user_id: ID of the user
            date: Date to optimize schedule for, defaults to today
            
        Returns:
            list: List of optimized tasks
        """
        if not date:
            date = datetime.now().date()
        
        # Get user preferences
        user_pref = UserPreference.query.filter_by(user_id=user_id).first()
        if not user_pref:
            logger.warning(f"No preferences found for user {user_id}")
            return []
        
        # Get all tasks for the date
        start_of_day = datetime.combine(date, datetime.min.time())
        end_of_day = datetime.combine(date, datetime.max.time())
        
        tasks = Task.query.filter(
            Task.user_id == user_id,
            Task.due_date.between(start_of_day, end_of_day),
            Task.status == 'pending'
        ).order_by(Task.ml_priority_score.desc()).all()
        
        if not tasks:
            return []
        
        # Get working hours
        working_start = datetime.combine(date, user_pref.working_hours_start)
        working_end = datetime.combine(date, user_pref.working_hours_end)
        
        # Check if we're past working hours for today
        now = datetime.now()
        if now.date() == date and now > working_end:
            # We're past today's working hours, return tasks as-is
            return tasks
        
        # Start time for scheduling (use current time if we're in the working day)
        current_time = max(working_start, now) if now.date() == date else working_start
        
        # Get productivity peak hours
        peak_hours = []
        try:
            raw_peak_hours = user_pref.get_productivity_peak_hours()
            for peak_period in raw_peak_hours:
                start_str, end_str = peak_period.split('-')
                start_hour, start_min = map(int, start_str.split(':'))
                end_hour, end_min = map(int, end_str.split(':'))
                
                peak_start = datetime.combine(date, datetime.min.time().replace(hour=start_hour, minute=start_min))
                peak_end = datetime.combine(date, datetime.min.time().replace(hour=end_hour, minute=end_min))
                
                peak_hours.append((peak_start, peak_end))
        except:
            # In case of error, use whole working day as peak hours
            peak_hours = [(working_start, working_end)]
        
        # Filter to current and future peak hours
        valid_peak_hours = []
        for start, end in peak_hours:
            if end >= current_time:
                valid_peak_hours.append((max(start, current_time), end))
        
        if not valid_peak_hours:
            # No valid peak hours left, use remaining work day
            valid_peak_hours = [(current_time, working_end)]
        
        # Sort tasks by ML priority score
        tasks.sort(key=lambda t: t.ml_priority_score, reverse=True)
        
        # Map of task ID to original time slot
        original_slots = {
            task.id: (task.start_time, task.end_time)
            for task in tasks
            if task.start_time and task.end_time
        }
        
        # Reset task times for rescheduling
        for task in tasks:
            if task.start_time and task.end_time and task.start_time >= current_time:
                # Only reset future tasks
                task.start_time = None
                task.end_time = None
        
        # Schedule tasks in priority order
        current_peak_idx = 0
        current_slot_start = valid_peak_hours[0][0]
        
        for task in tasks:
            if task.start_time and task.end_time:
                # Skip tasks that already have fixed times
                continue
            
            # Determine task duration
            if task.id in original_slots and original_slots[task.id][0] and original_slots[task.id][1]:
                # Use original duration
                orig_start, orig_end = original_slots[task.id]
                duration = (orig_end - orig_start).total_seconds() / 60
            else:
                # Use preferred task duration from user preferences
                duration = user_pref.preferred_task_duration
            
            # Find a suitable slot
            task_scheduled = False
            while not task_scheduled and current_peak_idx < len(valid_peak_hours):
                peak_start, peak_end = valid_peak_hours[current_peak_idx]
                
                if current_slot_start >= peak_end:
                    # Move to next peak period
                    current_peak_idx += 1
                    if current_peak_idx < len(valid_peak_hours):
                        current_slot_start = valid_peak_hours[current_peak_idx][0]
                    continue
                
                # Calculate potential end time
                potential_end = current_slot_start + timedelta(minutes=duration)
                
                if potential_end <= peak_end:
                    # We can fit the task in this slot
                    task.start_time = current_slot_start
                    task.end_time = potential_end
                    
                    # Add a small break after the task
                    current_slot_start = potential_end + timedelta(minutes=5)
                    task_scheduled = True
                else:
                    # Not enough time in current peak period, move to next
                    current_peak_idx += 1
                    if current_peak_idx < len(valid_peak_hours):
                        current_slot_start = valid_peak_hours[current_peak_idx][0]
            
            if not task_scheduled:
                # Couldn't schedule the task within working hours
                # Keep original times if available
                if task.id in original_slots:
                    task.start_time, task.end_time = original_slots[task.id]
                else:
                    # Schedule for next day if not scheduled
                    next_day = date + timedelta(days=1)
                    next_day_start = datetime.combine(next_day, user_pref.working_hours_start)
                    task.start_time = next_day_start
                    task.end_time = next_day_start + timedelta(minutes=duration)
        
        # Update database
        db.session.commit()
        
        return tasks
    
    def create_reminder(self, task, user):
        """
        Create reminders for a task based on user preferences.
        
        Args:
            task: The Task object
            user: The User object
        """
        # Check if user has preferences
        user_pref = UserPreference.query.filter_by(user_id=user.id).first()
        
        # Calculate reminder time (default: 30 minutes before task start)
        reminder_offset = 30  # minutes
        if user_pref:
            # Could have user preference for reminder timing
            pass
        
        # Determine when to send reminder
        if task.start_time:
            remind_at = task.start_time - timedelta(minutes=reminder_offset)
            
            # Don't create reminders for past times
            if remind_at > datetime.now():
                reminder = Reminder(
                    task_id=task.id,
                    remind_at=remind_at,
                    type='email'  # default to email
                )
                db.session.add(reminder)
                db.session.commit()
                logger.debug(f"Created reminder for task {task.id} at {remind_at}")
    
    def update_reminders(self, task):
        """
        Update reminders for a modified task.
        
        Args:
            task: The updated Task object
        """
        # Delete existing reminders for this task
        Reminder.query.filter_by(task_id=task.id).delete()
        
        # Only create new reminders if the task is pending
        if task.status == 'pending':
            # Calculate reminder time
            reminder_offset = 30  # minutes
            
            # Determine when to send reminder
            if task.start_time:
                remind_at = task.start_time - timedelta(minutes=reminder_offset)
                
                # Don't create reminders for past times
                if remind_at > datetime.now():
                    reminder = Reminder(
                        task_id=task.id,
                        remind_at=remind_at,
                        type='email'  # default to email
                    )
                    db.session.add(reminder)
                    db.session.commit()
                    logger.debug(f"Updated reminder for task {task.id} at {remind_at}")
    
    def get_tasks_for_timeframe(self, user_id, timeframe='today'):
        """
        Get tasks for a specific timeframe.
        
        Args:
            user_id: ID of the user
            timeframe: String indicating the timeframe (today, tomorrow, this_week, etc.)
            
        Returns:
            list: List of Task objects
        """
        now = datetime.now()
        
        if timeframe == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1) - timedelta(microseconds=1)
        elif timeframe == 'tomorrow':
            start_date = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1) - timedelta(microseconds=1)
        elif timeframe == 'this_week':
            # Start of week (Monday)
            start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=7) - timedelta(microseconds=1)
        elif timeframe == 'next_week':
            # Start of next week (next Monday)
            start_date = (now + timedelta(days=7-now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=7) - timedelta(microseconds=1)
        elif timeframe == 'this_month':
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # First day of next month - 1 microsecond
            if now.month == 12:
                end_date = datetime(now.year+1, 1, 1) - timedelta(microseconds=1)
            else:
                end_date = datetime(now.year, now.month+1, 1) - timedelta(microseconds=1)
        elif timeframe == 'upcoming':
            start_date = now
            end_date = now + timedelta(days=30)  # Next 30 days
        else:
            # Default to all pending tasks
            tasks = Task.query.filter_by(
                user_id=user_id,
                status='pending'
            ).order_by(Task.due_date).all()
            return tasks
        
        # Query for the specified timeframe
        tasks = Task.query.filter(
            Task.user_id == user_id,
            Task.due_date.between(start_date, end_date)
        ).order_by(Task.due_date).all()
        
        return tasks
