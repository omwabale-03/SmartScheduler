/**
 * Chart utilities for TimeMaster dashboard and analytics
 */

// Create task completion chart
function createCompletionChart(elementId, completedTasks, totalTasks) {
    const ctx = document.getElementById(elementId).getContext('2d');
    
    // Calculate pending tasks
    const pendingTasks = totalTasks - completedTasks;
    
    // Completion percentage
    const completionPercentage = totalTasks > 0 ? 
        Math.round((completedTasks / totalTasks) * 100) : 0;
    
    // Create chart
    const chart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Completed', 'Pending'],
            datasets: [{
                data: [completedTasks, pendingTasks],
                backgroundColor: ['#28a745', '#6c757d'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '75%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#f8f9fa',
                        padding: 10,
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.raw || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = Math.round((value / total) * 100);
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        },
        plugins: [{
            id: 'centerText',
            afterDraw: function(chart) {
                const width = chart.width;
                const height = chart.height;
                const ctx = chart.ctx;
                
                ctx.restore();
                ctx.font = 'bold 24px Arial';
                ctx.textBaseline = 'middle';
                ctx.textAlign = 'center';
                ctx.fillStyle = '#f8f9fa';
                
                // Display percentage in center
                ctx.fillText(`${completionPercentage}%`, width / 2, height / 2);
                
                ctx.font = '14px Arial';
                ctx.fillText('Completed', width / 2, (height / 2) + 25);
                ctx.save();
            }
        }]
    });
    
    return chart;
}

// Create priority distribution chart
function createPriorityChart(elementId, priorityData) {
    const ctx = document.getElementById(elementId).getContext('2d');
    
    const chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Low', 'Medium', 'High'],
            datasets: [{
                label: 'Tasks by Priority',
                data: [
                    priorityData.low || 0,
                    priorityData.medium || 0,
                    priorityData.high || 0
                ],
                backgroundColor: [
                    '#17a2b8', // info - low
                    '#ffc107', // warning - medium
                    '#dc3545'  // danger - high
                ],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        precision: 0,
                        color: '#f8f9fa'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                },
                x: {
                    ticks: {
                        color: '#f8f9fa'
                    },
                    grid: {
                        display: false
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const value = context.raw || 0;
                            return `${value} task${value !== 1 ? 's' : ''}`;
                        }
                    }
                }
            }
        }
    });
    
    return chart;
}

// Create task distribution by category chart
function createCategoryChart(elementId, categoryData) {
    const ctx = document.getElementById(elementId).getContext('2d');
    
    // Extract data
    const categories = Object.keys(categoryData);
    const counts = categories.map(category => categoryData[category]);
    
    // Define a set of colors
    const backgroundColors = [
        '#007bff', '#28a745', '#ffc107', '#dc3545', 
        '#17a2b8', '#6f42c1', '#fd7e14', '#20c997'
    ];
    
    const chart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: categories,
            datasets: [{
                data: counts,
                backgroundColor: categories.map((_, i) => backgroundColors[i % backgroundColors.length]),
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#f8f9fa',
                        padding: 10,
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                }
            }
        }
    });
    
    return chart;
}

// Create task schedule timeline
function createTimelineChart(elementId, taskData) {
    const ctx = document.getElementById(elementId).getContext('2d');
    
    // Extract task start times and durations
    const datasets = [];
    
    // Group tasks by categories for cleaner visualization
    const tasksByCategory = {};
    
    taskData.forEach(task => {
        if (!task.start_time || !task.end_time) return;
        
        const category = task.category || 'Uncategorized';
        if (!tasksByCategory[category]) {
            tasksByCategory[category] = [];
        }
        
        tasksByCategory[category].push({
            name: task.title,
            start: new Date(task.start_time),
            end: new Date(task.end_time)
        });
    });
    
    // Colors for categories
    const categoryColors = {
        'Work': '#007bff',
        'Personal': '#28a745',
        'Meeting': '#ffc107',
        'Health': '#dc3545',
        'Social': '#17a2b8',
        'Education': '#6f42c1',
        'Finance': '#fd7e14',
        'Shopping': '#20c997',
        'Travel': '#6610f2',
        'Uncategorized': '#6c757d'
    };
    
    // Build datasets
    let datasetIndex = 0;
    Object.keys(tasksByCategory).forEach(category => {
        const tasks = tasksByCategory[category];
        const color = categoryColors[category] || `hsl(${datasetIndex * 30}, 70%, 60%)`;
        
        datasets.push({
            label: category,
            data: tasks.map(task => ({
                x: [task.start, task.end],
                y: task.name
            })),
            backgroundColor: color,
            borderWidth: 0
        });
        
        datasetIndex++;
    });
    
    // Create chart
    const chart = new Chart(ctx, {
        type: 'bar',
        data: {
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'hour',
                        displayFormats: {
                            hour: 'HH:mm'
                        }
                    },
                    ticks: {
                        color: '#f8f9fa'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                },
                y: {
                    ticks: {
                        color: '#f8f9fa'
                    },
                    grid: {
                        display: false
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#f8f9fa'
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const task = context.raw;
                            const start = new Date(task.x[0]).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                            const end = new Date(task.x[1]).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                            return `${start} - ${end}`;
                        }
                    }
                }
            }
        }
    });
    
    return chart;
}
