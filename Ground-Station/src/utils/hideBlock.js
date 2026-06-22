function toggleDisplay() {
    const dataDisplay = document.getElementById('dataDisplay');
    dataDisplay.classList.toggle('collapsed'); // Toggle class to show or hide content
}

function toggleSettingsDisplay() {
    const settingsDisplay = document.getElementById('settingsDisplay');
    const toggleIcon = document.getElementById('toggle-icon');
    settingsDisplay.classList.toggle('collapsed'); // Toggle class name to show or hide content

}

function toggleLeftSidebar() {
    const sidebar = document.getElementById('leftSidebar');
    sidebar.classList.toggle('collapsed'); // Toggle class name to show or hide content
}

function toggleRealtime() {
    const sidebar = document.getElementById('photoPanel');
    sidebar.classList.toggle('collapsed'); // Toggle class name to show or hide content
}


function alwaysDisplayData() {
    const dataDisplay = document.getElementById('dataDisplay');
    
    // Force-remove 'collapsed' to ensure content is expanded
    if (dataDisplay.classList.contains('collapsed')) {
        dataDisplay.classList.remove('collapsed');
    }
}

function alwwaysDisplayRealtime() {
    const sidebar = document.getElementById('photoPanel');
    // Force-remove 'collapsed' to ensure content is expanded
    if (sidebar.classList.contains('collapsed')) {
        sidebar.classList.remove('collapsed');
    }
}