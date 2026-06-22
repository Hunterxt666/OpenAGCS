function updateTime() {
    const now = new Date();
    const year = String(now.getFullYear()).padStart(4, '0');
    const mon = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    const timeString = `⏱${year}-${mon}-${day} ${hours}:${minutes}:${seconds}`;

    // Update displayed text
    document.getElementById('timeDisplay').innerText = timeString;
}

// Show time immediately on page load
updateTime();
        
// Update time every second
setInterval(updateTime, 1000);