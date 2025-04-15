import os
import logging
import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from flask import url_for, session
import json

logger = logging.getLogger(__name__)

# Google Calendar API scopes
SCOPES = ['https://www.googleapis.com/auth/calendar']
API_SERVICE_NAME = 'calendar'
API_VERSION = 'v3'


class CalendarIntegration:
    def __init__(self):
        self.client_id = os.environ.get('GOOGLE_CLIENT_ID')
        self.client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
        self.redirect_uri = os.environ.get('CALENDAR_REDIRECT_URI')
        
        logger.debug("Calendar integration initialized")
    
    def get_authorization_url(self, user_id):
        """
        Get the Google OAuth2 authorization URL.
        
        Args:
            user_id: ID of the user
            
        Returns:
            str: Authorization URL
        """
        try:
            # Create flow instance
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [self.redirect_uri]
                    }
                },
                scopes=SCOPES
            )
            
            # Set the redirect URI
            flow.redirect_uri = self.redirect_uri
            
            # Generate URL for request to Google's OAuth 2.0 server
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            
            # Store the state in the session for later validation
            session['oauth_state'] = state
            session['oauth_user_id'] = user_id
            
            return authorization_url
        except Exception as e:
            logger.error(f"Error getting authorization URL: {str(e)}")
            return None
    
    def handle_oauth_callback(self, state, code):
        """
        Handle the OAuth callback from Google.
        
        Args:
            state: OAuth state parameter
            code: Authorization code
            
        Returns:
            dict: User credentials
        """
        # Verify state matches
        if state != session.get('oauth_state'):
            logger.error("State parameter doesn't match")
            return None
        
        try:
            # Create flow instance
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [self.redirect_uri]
                    }
                },
                scopes=SCOPES
            )
            
            flow.redirect_uri = self.redirect_uri
            
            # Use the authorization code to get credentials
            flow.fetch_token(code=code)
            
            # Get the credentials
            credentials = flow.credentials
            
            # Convert credentials to a dictionary
            creds_dict = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }
            
            return creds_dict
        except Exception as e:
            logger.error(f"Error handling OAuth callback: {str(e)}")
            return None
    
    def _get_credentials(self, creds_json):
        """
        Create Credentials object from stored JSON credentials.
        
        Args:
            creds_json: JSON string of credentials
            
        Returns:
            Credentials: Google OAuth credentials
        """
        try:
            creds_dict = json.loads(creds_json)
            return Credentials(
                token=creds_dict.get('token'),
                refresh_token=creds_dict.get('refresh_token'),
                token_uri=creds_dict.get('token_uri'),
                client_id=creds_dict.get('client_id'),
                client_secret=creds_dict.get('client_secret'),
                scopes=creds_dict.get('scopes')
            )
        except Exception as e:
            logger.error(f"Error creating credentials: {str(e)}")
            return None
    
    def create_calendar_event(self, creds_json, task):
        """
        Create a Google Calendar event for a task.
        
        Args:
            creds_json: JSON string of user's Google credentials
            task: The Task object
            
        Returns:
            str: ID of the created event, or None if failed
        """
        # Check if task has required time information
        if not task.start_time or not task.end_time:
            logger.warning(f"Task {task.id} missing start or end time")
            return None
        
        # Get credentials
        credentials = self._get_credentials(creds_json)
        if not credentials:
            return None
        
        try:
            # Build the service
            service = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
            
            # Create event details
            event = {
                'summary': task.title,
                'description': task.description,
                'start': {
                    'dateTime': task.start_time.isoformat(),
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': task.end_time.isoformat(),
                    'timeZone': 'UTC',
                },
                'reminders': {
                    'useDefault': True
                }
            }
            
            # Add calendar event
            event = service.events().insert(calendarId='primary', body=event).execute()
            logger.debug(f"Calendar event created with ID: {event.get('id')}")
            
            return event.get('id')
        except HttpError as e:
            logger.error(f"Error creating calendar event: {str(e)}")
            return None
    
    def update_calendar_event(self, creds_json, task):
        """
        Update a Google Calendar event for a task.
        
        Args:
            creds_json: JSON string of user's Google credentials
            task: The Task object
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Check if task has a calendar event ID
        if not task.calendar_event_id:
            logger.warning(f"Task {task.id} has no calendar event ID")
            return False
        
        # Get credentials
        credentials = self._get_credentials(creds_json)
        if not credentials:
            return False
        
        try:
            # Build the service
            service = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
            
            # Check if event exists
            try:
                event = service.events().get(
                    calendarId='primary', 
                    eventId=task.calendar_event_id
                ).execute()
            except HttpError:
                logger.warning(f"Event {task.calendar_event_id} not found")
                return False
            
            # Update event details
            event['summary'] = task.title
            event['description'] = task.description
            
            if task.start_time:
                event['start'] = {
                    'dateTime': task.start_time.isoformat(),
                    'timeZone': 'UTC',
                }
            
            if task.end_time:
                event['end'] = {
                    'dateTime': task.end_time.isoformat(),
                    'timeZone': 'UTC',
                }
            
            # Update the event
            updated_event = service.events().update(
                calendarId='primary',
                eventId=task.calendar_event_id,
                body=event
            ).execute()
            
            logger.debug(f"Updated calendar event {updated_event.get('id')}")
            return True
        except HttpError as e:
            logger.error(f"Error updating calendar event: {str(e)}")
            return False
    
    def delete_calendar_event(self, creds_json, event_id):
        """
        Delete a Google Calendar event.
        
        Args:
            creds_json: JSON string of user's Google credentials
            event_id: ID of the event to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Get credentials
        credentials = self._get_credentials(creds_json)
        if not credentials:
            return False
        
        try:
            # Build the service
            service = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
            
            # Delete the event
            service.events().delete(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            logger.debug(f"Deleted calendar event {event_id}")
            return True
        except HttpError as e:
            logger.error(f"Error deleting calendar event: {str(e)}")
            return False
    
    def sync_calendar_events(self, creds_json, user_id, from_date=None, to_date=None):
        """
        Sync events from Google Calendar to the app.
        
        Args:
            creds_json: JSON string of user's Google credentials
            user_id: ID of the user
            from_date: Start date for sync (optional)
            to_date: End date for sync (optional)
            
        Returns:
            dict: Sync results
        """
        # Get credentials
        credentials = self._get_credentials(creds_json)
        if not credentials:
            return {
                'success': False,
                'message': 'Invalid credentials'
            }
        
        # Set default date range if not provided
        if not from_date:
            from_date = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if not to_date:
            to_date = from_date + datetime.timedelta(days=30)
        
        try:
            # Build the service
            service = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
            
            # Format time range for API
            time_min = from_date.isoformat() + 'Z'
            time_max = to_date.isoformat() + 'Z'
            
            # Get events from calendar
            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            if not events:
                return {
                    'success': True,
                    'message': 'No events found to sync',
                    'synced': 0
                }
            
            # Process events
            # Implementation would depend on how we want to sync events
            # For now, return basic info
            
            return {
                'success': True,
                'message': f'Found {len(events)} events',
                'events': len(events)
            }
        except HttpError as e:
            logger.error(f"Error syncing calendar events: {str(e)}")
            return {
                'success': False,
                'message': f'Error syncing: {str(e)}'
            }
