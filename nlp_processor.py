import spacy
import logging
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)

# Load the English NLP model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    # If the model isn't found, download it
    import subprocess
    subprocess.call([
        "python", "-m", "spacy", "download", "en_core_web_sm"
    ])
    nlp = spacy.load("en_core_web_sm")

# Define patterns for date and time extraction
DATE_PATTERNS = [
    r'today',
    r'tomorrow',
    r'next (monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
    r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
    r'next week',
    r'next month',
    r'(\d{1,2})(?:st|nd|rd|th)?[ ,-]*(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:[ ,-]*(\d{4}))?',
    r'(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?',
]

TIME_PATTERNS = [
    r'(\d{1,2})(?::(\d{2}))?[ ]*(am|pm)?',
    r'(\d{1,2})(?::(\d{2}))?[ ]*(a\.m\.|p\.m\.)?',
    r'(\d{1,2})(?::(\d{2}))?[ ]*(a|p)?',
    r'at (\d{1,2})(?::(\d{2}))?[ ]*(am|pm)?',
    r'morning',
    r'afternoon',
    r'evening',
    r'noon',
    r'midnight',
]

DURATION_PATTERNS = [
    r'for (\d+) min(?:ute(?:s)?)?',
    r'for (\d+) hour(?:s)?',
    r'for (\d+) day(?:s)?',
    r'for (\d+) week(?:s)?',
    r'for (\d+) month(?:s)?',
]

PRIORITY_KEYWORDS = {
    'high': ['urgent', 'important', 'critical', 'asap', 'high priority', 'essential', 'vital'],
    'medium': ['medium priority', 'significant', 'moderate', 'relevant'],
    'low': ['low priority', 'minor', 'trivial', 'when possible', 'not urgent']
}

# Mapping of day names to their index in a week (0-6, where 0 is Monday)
DAY_NAME_TO_INDEX = {
    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
    'friday': 4, 'saturday': 5, 'sunday': 6
}


class NLPProcessor:
    def __init__(self):
        self.nlp = nlp
        logger.debug("NLP processor initialized")
    
    def extract_task_info(self, text):
        """
        Extract task information from natural language text.
        Returns a dictionary with extracted task details.
        """
        doc = self.nlp(text.lower())
        
        # Initialize task data dictionary
        task_data = {
            'title': '',
            'description': '',
            'due_date': None,
            'start_time': None,
            'end_time': None,
            'priority': 0,
            'category': None,
            'duration': None,
        }
        
        # Extract task title (using the main verb and its direct object)
        verbs = [token for token in doc if token.pos_ == "VERB"]
        if verbs:
            main_verb = verbs[0]
            # Get the verb phrase and its object
            obj_text = ""
            for token in doc:
                if token.head == main_verb and token.dep_ in ["dobj", "pobj"]:
                    # Get the entire object phrase
                    obj_phrase = [t for t in token.subtree]
                    obj_text = " ".join([t.text for t in sorted(obj_phrase, key=lambda t: t.i)])
                    break
            
            if obj_text:
                task_data['title'] = f"{main_verb.text} {obj_text}"
            else:
                # If no direct object found, use the verb and next few tokens
                verb_idx = main_verb.i
                title_end = min(verb_idx + 5, len(doc))
                task_data['title'] = " ".join([t.text for t in doc[verb_idx:title_end]])
        
        # If no title was extracted, use first few tokens of the input
        if not task_data['title']:
            task_data['title'] = " ".join([t.text for t in doc[:min(6, len(doc))]])
        
        # Extract the description (use the whole text as a starting point)
        task_data['description'] = text
        
        # Extract dates and times
        dates_times = self._extract_dates_times(text)
        if 'due_date' in dates_times:
            task_data['due_date'] = dates_times['due_date']
        if 'start_time' in dates_times:
            task_data['start_time'] = dates_times['start_time']
        if 'end_time' in dates_times:
            task_data['end_time'] = dates_times['end_time']
        if 'duration' in dates_times:
            task_data['duration'] = dates_times['duration']
        
        # Extract priority
        task_data['priority'] = self._extract_priority(text)
        
        # Extract category using entity recognition
        categories = []
        for ent in doc.ents:
            if ent.label_ in ["ORG", "PRODUCT", "EVENT", "WORK_OF_ART"]:
                categories.append(ent.text)
        
        # Also look for common category words
        category_words = ["work", "personal", "health", "meeting", "appointment", "project", 
                         "family", "social", "education", "finance", "shopping", "travel"]
        for word in category_words:
            if word in text.lower():
                categories.append(word)
        
        if categories:
            task_data['category'] = categories[0]  # Use the first identified category
        
        return task_data
    
    def _extract_dates_times(self, text):
        """Extract dates and times from the text"""
        text = text.lower()
        result = {}
        
        # Current date/time for reference
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Extract dates
        for pattern in DATE_PATTERNS:
            matches = re.finditer(pattern, text)
            for match in matches:
                date_str = match.group(0)
                
                if 'today' in date_str:
                    extracted_date = today
                elif 'tomorrow' in date_str:
                    extracted_date = today + timedelta(days=1)
                elif 'next ' in date_str and any(day in date_str for day in DAY_NAME_TO_INDEX.keys()):
                    # Handle "next Monday", "next Tuesday", etc.
                    for day_name in DAY_NAME_TO_INDEX.keys():
                        if day_name in date_str:
                            days_ahead = DAY_NAME_TO_INDEX[day_name] - today.weekday()
                            if days_ahead <= 0:  # Target day is today or earlier this week
                                days_ahead += 7  # Go to next week
                            extracted_date = today + timedelta(days=days_ahead)
                            break
                elif any(day in date_str for day in DAY_NAME_TO_INDEX.keys()):
                    # Handle just "Monday", "Tuesday", etc.
                    for day_name in DAY_NAME_TO_INDEX.keys():
                        if day_name in date_str:
                            days_ahead = DAY_NAME_TO_INDEX[day_name] - today.weekday()
                            if days_ahead <= 0:  # Target day is today or earlier this week
                                days_ahead += 7  # Go to next week
                            extracted_date = today + timedelta(days=days_ahead)
                            break
                elif 'next week' in date_str:
                    # Next Monday
                    days_until_next_week = 7 - today.weekday()
                    extracted_date = today + timedelta(days=days_until_next_week)
                elif 'next month' in date_str:
                    if now.month == 12:
                        extracted_date = now.replace(year=now.year+1, month=1, day=1)
                    else:
                        extracted_date = now.replace(month=now.month+1, day=1)
                else:
                    # Try to parse specific date formats
                    try:
                        # Will need more complex parsing for various date formats
                        # This is a simplified version
                        if re.match(r'(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?', date_str):
                            parts = re.match(r'(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?', date_str)
                            month = int(parts.group(1))
                            day = int(parts.group(2))
                            year = int(parts.group(3)) if parts.group(3) else now.year
                            if year < 100:  # Handle two-digit years
                                year = 2000 + year if year < 50 else 1900 + year
                            extracted_date = datetime(year, month, day)
                        else:
                            continue
                    except:
                        continue
                
                if 'due_date' not in result:
                    result['due_date'] = extracted_date
                elif 'start_time' not in result:
                    result['start_time'] = extracted_date
        
        # Extract times
        time_matches = []
        for pattern in TIME_PATTERNS:
            matches = re.finditer(pattern, text)
            for match in matches:
                time_str = match.group(0)
                time_matches.append((time_str, match.span()))
        
        # Sort time matches by position in text
        time_matches.sort(key=lambda x: x[1][0])
        
        # Process time matches
        for i, (time_str, _) in enumerate(time_matches):
            try:
                hour, minute = 0, 0
                
                if 'morning' in time_str:
                    hour, minute = 9, 0
                elif 'afternoon' in time_str:
                    hour, minute = 14, 0
                elif 'evening' in time_str:
                    hour, minute = 18, 0
                elif 'noon' in time_str:
                    hour, minute = 12, 0
                elif 'midnight' in time_str:
                    hour, minute = 0, 0
                else:
                    # Parse HH:MM format
                    hour_match = re.search(r'(\d{1,2})', time_str)
                    if hour_match:
                        hour = int(hour_match.group(1))
                        minute_match = re.search(r':(\d{2})', time_str)
                        minute = int(minute_match.group(1)) if minute_match else 0
                        
                        # Handle AM/PM
                        if 'pm' in time_str.lower() or 'p.m.' in time_str.lower() or ' p' in time_str.lower():
                            if hour < 12:
                                hour += 12
                        elif ('am' in time_str.lower() or 'a.m.' in time_str.lower() or ' a' in time_str.lower()) and hour == 12:
                            hour = 0
                
                # Set the time on the appropriate date
                time_date = result.get('due_date', today)
                time_datetime = time_date.replace(hour=hour, minute=minute)
                
                if i == 0 and 'start_time' not in result:
                    result['start_time'] = time_datetime
                elif i == 1 or 'end_time' not in result:
                    result['end_time'] = time_datetime
            except:
                continue
        
        # Extract duration
        for pattern in DURATION_PATTERNS:
            match = re.search(pattern, text)
            if match:
                duration_value = int(match.group(1))
                if 'minute' in match.group(0):
                    result['duration'] = duration_value
                elif 'hour' in match.group(0):
                    result['duration'] = duration_value * 60
                elif 'day' in match.group(0):
                    result['duration'] = duration_value * 24 * 60
                break
        
        # If we have a start time and duration but no end time, calculate the end time
        if 'start_time' in result and 'duration' in result and 'end_time' not in result:
            result['end_time'] = result['start_time'] + timedelta(minutes=result['duration'])
        
        return result
    
    def _extract_priority(self, text):
        """Extract priority level from text"""
        text_lower = text.lower()
        
        # Check for explicit priority indications
        if any(word in text_lower for word in PRIORITY_KEYWORDS['high']):
            return 5
        elif any(word in text_lower for word in PRIORITY_KEYWORDS['medium']):
            return 3
        elif any(word in text_lower for word in PRIORITY_KEYWORDS['low']):
            return 1
        
        # Default priority if none specified
        return 0
    
    def understand_command(self, text):
        """
        Understand the type of command the user is giving.
        Returns a dictionary with command type and relevant extracted info.
        """
        text_lower = text.lower()
        result = {'command_type': 'unknown', 'data': {}}
        
        # Check for task creation commands
        if any(phrase in text_lower for phrase in [
            'add task', 'create task', 'new task', 'schedule', 'remind me', 
            'set up', 'plan', 'organize', 'arrange'
        ]):
            result['command_type'] = 'create_task'
            result['data'] = self.extract_task_info(text)
        
        # Check for task listing/viewing commands
        elif any(phrase in text_lower for phrase in [
            'show task', 'show all task', 'list task', 'view task', 
            'what are my task', 'display task', 'get task', 'show my task'
        ]):
            result['command_type'] = 'list_tasks'
            
            # Check for filtering criteria
            if 'today' in text_lower:
                result['data']['timeframe'] = 'today'
            elif 'tomorrow' in text_lower:
                result['data']['timeframe'] = 'tomorrow'
            elif 'this week' in text_lower:
                result['data']['timeframe'] = 'this_week'
            elif 'next week' in text_lower:
                result['data']['timeframe'] = 'next_week'
            elif 'high priority' in text_lower or 'important' in text_lower:
                result['data']['priority'] = 'high'
            
            # Default to today if no timeframe specified
            if 'timeframe' not in result['data']:
                result['data']['timeframe'] = 'today'
            
            # Extract category if mentioned
            doc = self.nlp(text_lower)
            for token in doc:
                if token.text in ['work', 'personal', 'health', 'meeting', 'project', 'social']:
                    result['data']['category'] = token.text
                    break
        
        
        # Check for task update commands
        elif any(phrase in text_lower for phrase in [
            'update task', 'change task', 'modify task', 'edit task',
            'reschedule', 'postpone', 'move task', 'mark as complete',
            'mark done', 'finish task', 'complete task'
        ]):
            result['command_type'] = 'update_task'
            
            # Check for task identification
            task_title = None
            doc = self.nlp(text)
            for token in doc:
                if token.dep_ in ['dobj', 'pobj']:
                    # Extract object phrase as potential task title
                    task_title = " ".join([t.text for t in token.subtree])
                    break
            
            if task_title:
                result['data']['task_title'] = task_title
            
            # Check for completion status
            if any(phrase in text_lower for phrase in ['complete', 'done', 'finish']):
                result['data']['status'] = 'completed'
            
            # Check for rescheduling
            dates_times = self._extract_dates_times(text)
            if dates_times:
                result['data'].update(dates_times)
        
        # Check for deletion commands
        elif any(phrase in text_lower for phrase in [
            'delete task', 'remove task', 'cancel task', 'eliminate task'
        ]):
            result['command_type'] = 'delete_task'
            
            # Try to extract task title to delete
            task_title = None
            doc = self.nlp(text)
            for token in doc:
                if token.dep_ in ['dobj', 'pobj']:
                    # Extract object phrase as potential task title
                    task_title = " ".join([t.text for t in token.subtree])
                    break
            
            if task_title:
                result['data']['task_title'] = task_title
        
        # Check for analytical commands
        elif any(phrase in text_lower for phrase in [
            'analyze', 'productivity', 'statistics', 'progress', 'report',
            'how am i doing', 'my performance', 'task completion'
        ]):
            result['command_type'] = 'analytics'
            
            # Check for time period
            if 'today' in text_lower:
                result['data']['timeframe'] = 'today'
            elif 'this week' in text_lower:
                result['data']['timeframe'] = 'this_week'
            elif 'this month' in text_lower:
                result['data']['timeframe'] = 'this_month'
            elif 'all time' in text_lower:
                result['data']['timeframe'] = 'all_time'
            else:
                result['data']['timeframe'] = 'all_time'  # Default to all time
        
        # Check for preference setting commands
        elif any(phrase in text_lower for phrase in [
            'settings', 'preferences', 'set preference', 'update preference',
            'change my', 'working hours', 'notification', 'configure'
        ]):
            result['command_type'] = 'preferences'
            
            # Extract specific preference settings
            if 'working hours' in text_lower:
                result['data']['preference_type'] = 'working_hours'
                times = self._extract_dates_times(text)
                if 'start_time' in times:
                    result['data']['start_time'] = times['start_time']
                if 'end_time' in times:
                    result['data']['end_time'] = times['end_time']
            
            elif 'notification' in text_lower:
                result['data']['preference_type'] = 'notifications'
                if 'email' in text_lower:
                    result['data']['notification_medium'] = 'email'
                elif 'reminder' in text_lower:
                    result['data']['notification_medium'] = 'reminder'
            
            elif 'break' in text_lower:
                result['data']['preference_type'] = 'breaks'
                times = self._extract_dates_times(text)
                if 'duration' in times:
                    result['data']['break_duration'] = times['duration']
        
        # Check for help commands
        elif any(phrase in text_lower for phrase in [
            'help', 'how to', 'instructions', 'guide me', 'tutorial', 'what can you do'
        ]):
            result['command_type'] = 'help'
        
        # Check for calendar sync commands
        elif any(phrase in text_lower for phrase in [
            'sync calendar', 'connect calendar', 'google calendar', 'link calendar'
        ]):
            result['command_type'] = 'calendar_sync'
        
        return result
