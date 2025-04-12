import logging
import numpy as np
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from app import db
from models import Task, UserActivity

logger = logging.getLogger(__name__)

class MLPrioritizer:
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        logger.debug("ML prioritizer initialized")
    
    def extract_features(self, task, user_tasks=None, current_time=None):
        """
        Extract features from a task for ML prioritization.
        
        Args:
            task: The Task object
            user_tasks: List of all user tasks (optional)
            current_time: Current datetime (optional, defaults to now)
            
        Returns:
            features: Numpy array of task features
        """
        if current_time is None:
            current_time = datetime.now()
        
        # Initialize features
        features = []
        
        # 1. Time to due date (in hours)
        if task.due_date:
            time_to_due = (task.due_date - current_time).total_seconds() / 3600
            # Cap at 168 hours (1 week)
            time_to_due = min(max(time_to_due, -24), 168)
        else:
            time_to_due = 168  # Default to 1 week if no due date
        
        features.append(time_to_due)
        
        # 2. Explicit priority (normalized)
        priority_norm = task.priority / 5.0
        features.append(priority_norm)
        
        # 3. Is there a calendar event associated?
        has_calendar_event = 1.0 if task.calendar_event_id else 0.0
        features.append(has_calendar_event)
        
        # 4. Task age (in days)
        task_age = (current_time - task.created_at).total_seconds() / (24 * 3600)
        features.append(min(task_age, 30))  # Cap at 30 days
        
        # 5. Is it in a peak productivity hour?
        in_peak_hour = 0.0
        if task.start_time:
            # This would need user preferences data to determine peak hours
            # Simplified version: assume 9 AM - 12 PM and 2 PM - 5 PM are peak hours
            hour = task.start_time.hour
            if (9 <= hour < 12) or (14 <= hour < 17):
                in_peak_hour = 1.0
        
        features.append(in_peak_hour)
        
        # 6. Similar tasks completed count (if user_tasks provided)
        similar_completed = 0
        if user_tasks:
            # Simple similarity: same category
            category = task.category
            if category:
                similar_completed = sum(
                    1 for t in user_tasks 
                    if t.category == category and t.status == 'completed'
                )
        
        # Normalize
        features.append(min(similar_completed / 10.0, 1.0))
        
        return np.array(features).reshape(1, -1)
    
    def train_model(self, user_id):
        """
        Train a machine learning model to predict task priority.
        
        Args:
            user_id: ID of the user
            
        Returns:
            bool: True if training successful, False otherwise
        """
        # Get completed tasks for this user (for training data)
        completed_tasks = Task.query.filter_by(
            user_id=user_id,
            status='completed'
        ).all()
        
        # Need enough tasks to train
        if len(completed_tasks) < 5:
            logger.warning(f"Not enough completed tasks to train model for user {user_id}")
            return False
        
        # Get all tasks for feature extraction context
        all_tasks = Task.query.filter_by(user_id=user_id).all()
        
        # Prepare features and target
        X = []
        y = []
        
        for task in completed_tasks:
            # Use task completion time as reference
            user_activity = UserActivity.query.filter_by(
                user_id=user_id,
                activity_type='task_completed',
                details=str(task.id)
            ).first()
            
            completion_time = user_activity.timestamp if user_activity else task.created_at
            
            # Extract features
            features = self.extract_features(task, all_tasks, completion_time)
            X.append(features.flatten())
            
            # Target: either explicit priority or derived from completion time
            # Here we use a combination of both
            explicit_priority = task.priority / 5.0
            
            # Time to completion: tasks completed sooner after creation are higher priority
            if completion_time and task.created_at:
                days_to_completion = (completion_time - task.created_at).total_seconds() / (24 * 3600)
                # Inverse relationship: quicker completion = higher priority
                time_priority = max(0, 1 - (days_to_completion / 7))  # Normalized to [0,1]
            else:
                time_priority = 0.5  # Default
            
            # Combined priority (weighted average)
            combined_priority = 0.7 * explicit_priority + 0.3 * time_priority
            y.append(combined_priority)
        
        # Convert to numpy arrays
        X = np.array(X)
        y = np.array(y)
        
        if len(X) == 0:
            logger.warning("No valid training data")
            return False
        
        # Scale features
        try:
            X_scaled = self.scaler.fit_transform(X)
            
            # Train Random Forest Regressor
            self.model = RandomForestRegressor(n_estimators=50, random_state=42)
            self.model.fit(X_scaled, y)
            
            logger.debug(f"ML model trained for user {user_id} with {len(X)} samples")
            return True
        except Exception as e:
            logger.error(f"Error training ML model: {str(e)}")
            return False
    
    def prioritize_task(self, task, user_tasks):
        """
        Calculate a priority score for a task.
        
        Args:
            task: The Task object
            user_tasks: List of all user tasks
            
        Returns:
            float: Priority score between 0-1
        """
        # Extract features
        features = self.extract_features(task, user_tasks)
        
        # If we have a trained model, use it
        if self.model:
            try:
                # Scale features
                features_scaled = self.scaler.transform(features)
                
                # Predict priority
                predicted_priority = self.model.predict(features_scaled)[0]
                return max(0, min(predicted_priority, 1))  # Clamp to [0,1]
            except Exception as e:
                logger.error(f"Error predicting priority: {str(e)}")
        
        # Fallback: rule-based prioritization
        return self._rule_based_priority(task)
    
    def _rule_based_priority(self, task):
        """
        Rule-based prioritization when ML model isn't available.
        
        Args:
            task: The Task object
            
        Returns:
            float: Priority score between 0-1
        """
        now = datetime.now()
        priority_score = 0.0
        
        # Factor 1: Explicit priority (0-5)
        priority_score += (task.priority / 5) * 0.4
        
        # Factor 2: Due date proximity
        if task.due_date:
            hours_until_due = max(-24, (task.due_date - now).total_seconds() / 3600)
            if hours_until_due < 0:
                # Overdue tasks
                proximity_score = 1.0
            elif hours_until_due < 24:
                # Due within 24 hours
                proximity_score = 0.8
            elif hours_until_due < 72:
                # Due within 3 days
                proximity_score = 0.6
            elif hours_until_due < 168:
                # Due within a week
                proximity_score = 0.4
            else:
                proximity_score = 0.2
        else:
            proximity_score = 0.1
        
        priority_score += proximity_score * 0.4
        
        # Factor 3: Has calendar event
        if task.calendar_event_id:
            priority_score += 0.1
        
        # Factor 4: Task age (older tasks get slight boost)
        if task.created_at:
            days_old = (now - task.created_at).total_seconds() / (24 * 3600)
            age_factor = min(days_old / 14, 1.0)  # Max boost after 2 weeks
            priority_score += age_factor * 0.1
        
        return priority_score
    
    def cluster_tasks(self, user_id):
        """
        Cluster tasks to find patterns and groupings.
        
        Args:
            user_id: ID of the user
            
        Returns:
            dict: Dictionary with cluster information
        """
        # Get tasks
        tasks = Task.query.filter_by(user_id=user_id).all()
        
        if len(tasks) < 5:
            logger.warning(f"Not enough tasks to perform clustering for user {user_id}")
            return {"success": False, "message": "Not enough tasks for meaningful clustering"}
        
        try:
            # Extract features for clustering
            features = []
            task_ids = []
            
            for task in tasks:
                # Get a simplified feature vector for clustering
                task_features = []
                
                # 1. Priority
                task_features.append(task.priority / 5.0)
                
                # 2. Time of day (for tasks with start time)
                if task.start_time:
                    # Normalize hour to [0,1]
                    hour_norm = (task.start_time.hour + task.start_time.minute/60) / 24
                    task_features.append(hour_norm)
                else:
                    task_features.append(0.5)  # Default to middle of day
                
                # 3. Day of week (for tasks with due date)
                if task.due_date:
                    # Normalize day of week to [0,1]
                    day_norm = task.due_date.weekday() / 6
                    task_features.append(day_norm)
                else:
                    task_features.append(0.5)  # Default to middle of week
                
                features.append(task_features)
                task_ids.append(task.id)
            
            # Convert to numpy array
            X = np.array(features)
            
            # Determine optimal number of clusters (2-5)
            k_values = range(2, min(6, len(X) + 1))
            inertias = []
            
            for k in k_values:
                kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
                kmeans.fit(X)
                inertias.append(kmeans.inertia_)
            
            # Find optimal k using elbow method
            optimal_k = 2
            if len(inertias) > 2:
                # Calculate the rate of decrease in inertia
                inertia_changes = [inertias[i-1] - inertias[i] for i in range(1, len(inertias))]
                
                # If the change decreases significantly, we found an elbow
                for i in range(1, len(inertia_changes)):
                    if inertia_changes[i] < inertia_changes[i-1] * 0.5:
                        optimal_k = k_values[i]
                        break
            
            # Perform clustering with optimal k
            kmeans = KMeans(n_clusters=optimal_k, random_state=42, n_init=10)
            clusters = kmeans.fit_predict(X)
            
            # Create result with task-to-cluster mapping
            result = {
                "success": True,
                "clusters": {},
                "task_clusters": {}
            }
            
            for i, cluster_id in enumerate(clusters):
                if cluster_id not in result["clusters"]:
                    result["clusters"][int(cluster_id)] = []
                
                task_id = task_ids[i]
                result["clusters"][int(cluster_id)].append(task_id)
                result["task_clusters"][task_id] = int(cluster_id)
            
            return result
        
        except Exception as e:
            logger.error(f"Error in task clustering: {str(e)}")
            return {"success": False, "message": str(e)}
    
    def update_all_task_priorities(self, user_id):
        """
        Update ML priority scores for all pending tasks of a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            int: Number of tasks updated
        """
        # Get all pending tasks
        tasks = Task.query.filter_by(
            user_id=user_id,
            status='pending'
        ).all()
        
        # Get all user tasks for context
        all_tasks = Task.query.filter_by(user_id=user_id).all()
        
        # Update priority score for each task
        count = 0
        for task in tasks:
            task.ml_priority_score = self.prioritize_task(task, all_tasks)
            count += 1
        
        # Save changes
        db.session.commit()
        
        logger.debug(f"Updated ML priority scores for {count} tasks for user {user_id}")
        return count
