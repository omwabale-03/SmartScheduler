// Main application JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
    
    // Initialize popovers
    const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
    const popoverList = [...popoverTriggerList].map(popoverTriggerEl => new bootstrap.Popover(popoverTriggerEl));
    
    // Flash message auto-hide
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert.alert-dismissible');
        alerts.forEach(function(alert) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
    
    // Mark task as complete buttons
    const completeButtons = document.querySelectorAll('.btn-complete-task');
    completeButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            if (!confirm('Mark this task as complete?')) {
                e.preventDefault();
            }
        });
    });
    
    // Delete task buttons
    const deleteButtons = document.querySelectorAll('.btn-delete-task');
    deleteButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            if (!confirm('Are you sure you want to delete this task?')) {
                e.preventDefault();
            }
        });
    });
    
    // Task priority display
    const priorityElements = document.querySelectorAll('.task-priority');
    priorityElements.forEach(function(element) {
        const priority = parseInt(element.dataset.priority);
        let color = 'secondary';
        
        if (priority >= 4) {
            color = 'danger';
        } else if (priority >= 2) {
            color = 'warning';
        } else if (priority >= 0) {
            color = 'info';
        }
        
        element.classList.add(`text-${color}`);
    });
    
    // Initialize assistant if it exists
    initializeAssistant();
});

// Assistant chat functionality
function initializeAssistant() {
    const assistantContainer = document.getElementById('assistant-container');
    if (!assistantContainer) return;
    
    const chatMessages = document.getElementById('chat-messages');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-message');
    
    // Add welcome message
    addMessage('system', "Hi there! I'm your AI time management assistant. How can I help you today? You can ask me to create tasks, check your schedule, or optimize your time.");
    
    // Send message on button click
    sendButton.addEventListener('click', sendMessage);
    
    // Send message on Enter key
    messageInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });
    
    function sendMessage() {
        const message = messageInput.value.trim();
        if (!message) return;
        
        // Add user message to chat
        addMessage('user', message);
        messageInput.value = '';
        
        // Show loading indicator
        addMessage('loading', '');
        
        // Send to backend
        fetch('/api/assistant/process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message: message }),
        })
        .then(response => response.json())
        .then(data => {
            // Remove loading indicator
            const loadingElem = document.querySelector('.message-loading');
            if (loadingElem) {
                chatMessages.removeChild(loadingElem);
            }
            
            // Process response
            processAssistantResponse(data);
        })
        .catch(error => {
            console.error('Error:', error);
            
            // Remove loading indicator
            const loadingElem = document.querySelector('.message-loading');
            if (loadingElem) {
                chatMessages.removeChild(loadingElem);
            }
            
            // Add error message
            addMessage('system', "Sorry, I encountered an error processing your request.");
        });
    }
    
    function processAssistantResponse(data) {
        if (!data.success) {
            addMessage('system', data.message || "Sorry, something went wrong.");
            return;
        }
        
        // Add main response message
        addMessage('system', data.message);
        
        // Handle additional data based on command type
        switch (data.command_type) {
            case 'list_tasks':
                if (data.tasks && data.tasks.length > 0) {
                    addTaskList(data.tasks);
                }
                break;
                
            case 'analytics':
                if (data.analytics) {
                    addAnalyticsView(data.analytics);
                }
                break;
                
            case 'calendar_sync':
                if (data.auth_url) {
                    addCalendarAuthLink(data.auth_url);
                }
                break;
        }
    }
    
    function addMessage(type, content) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', `message-${type}`);
        
        if (type === 'loading') {
            messageDiv.innerHTML = `
                <div class="spinner-border spinner-border-sm text-light" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <span class="ms-2">Thinking...</span>
            `;
        } else {
            // Escape HTML in user messages
            const safeContent = type === 'user' ? 
                content.replace(/</g, '&lt;').replace(/>/g, '&gt;') : 
                content;
                
            messageDiv.innerHTML = `
                <div class="message-content">
                    ${safeContent}
                </div>
            `;
        }
        
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    function addTaskList(tasks) {
        const tasksDiv = document.createElement('div');
        tasksDiv.classList.add('task-list-container');
        
        let tasksHtml = '<div class="assistant-tasks"><ul class="list-group">';
        
        tasks.forEach(task => {
            const dueDate = task.due_date ? new Date(task.due_date).toLocaleDateString() : 'No date';
            const startTime = task.start_time ? new Date(task.start_time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '';
            
            let priorityBadge = '';
            if (task.priority >= 4) {
                priorityBadge = '<span class="badge bg-danger ms-1">High</span>';
            } else if (task.priority >= 2) {
                priorityBadge = '<span class="badge bg-warning ms-1">Medium</span>';
            }
            
            tasksHtml += `
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    <div>
                        <strong>${task.title}</strong> ${priorityBadge}
                        <div class="text-muted small">${dueDate} ${startTime}</div>
                    </div>
                    <a href="/tasks/${task.id}" class="btn btn-sm btn-outline-info">View</a>
                </li>
            `;
        });
        
        tasksHtml += '</ul></div>';
        tasksDiv.innerHTML = tasksHtml;
        
        chatMessages.appendChild(tasksDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    function addAnalyticsView(analytics) {
        const analyticsDiv = document.createElement('div');
        analyticsDiv.classList.add('analytics-container', 'card', 'my-2');
        
        let completionRate = analytics.completion_rate || 0;
        
        let analyticsHtml = `
            <div class="card-body">
                <h5 class="card-title">Productivity Summary</h5>
                <div class="row">
                    <div class="col-md-6">
                        <p><strong>Tasks completed:</strong> ${analytics.completed_tasks}/${analytics.total_tasks}</p>
                        <p><strong>Completion rate:</strong> ${completionRate}%</p>
                        <p><strong>Avg. completion time:</strong> ${analytics.avg_completion_time_hours || 0} hours</p>
                    </div>
                    <div class="col-md-6">
                        <div class="chart-container" style="position: relative; height:150px;">
                            <canvas id="completionChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        analyticsDiv.innerHTML = analyticsHtml;
        chatMessages.appendChild(analyticsDiv);
        
        // Create chart
        const ctx = document.getElementById('completionChart').getContext('2d');
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Completed', 'Pending'],
                datasets: [{
                    data: [analytics.completed_tasks, (analytics.total_tasks - analytics.completed_tasks)],
                    backgroundColor: ['#28a745', '#6c757d'],
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#f8f9fa'
                        }
                    }
                }
            }
        });
        
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    function addCalendarAuthLink(authUrl) {
        const linkDiv = document.createElement('div');
        linkDiv.classList.add('calendar-auth-link', 'my-2');
        
        linkDiv.innerHTML = `
            <a href="${authUrl}" class="btn btn-primary" target="_blank">
                <i class="bi bi-calendar"></i> Connect Google Calendar
            </a>
        `;
        
        chatMessages.appendChild(linkDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}
