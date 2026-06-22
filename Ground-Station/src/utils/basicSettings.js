// Mission-control handlers for origin setup, tracking, takeoff, and return.
let has_init = false, has_depart = false, trackingInterval = null, videoInterval = null;
let api_timeout = 300, video_timeout = 500;

async function init_display(){
    const center = await fetchCenter();
    if (center.length == 0){
        alert("Origin is not set 🤯");
        return;
    }
    map.setCenter(center[0]);
    ugvway.push(center[0]);
    uavway.push(center[0]);
    ugv_passedPolyline.show();
    ugv_marker.setPosition(center[0]);
    uav_passedPolyline.show();
    uav_marker.setPosition(center[0]);
    home_marker.setPosition(center[0]);
    origin_time = center[1];
    home_marker.show();
    uav_marker.show();
    ugv_marker.show();
    setOriginTime(origin_time);
    startDataFilling();
    alwaysDisplayData();
    has_init = true;
    if (trackingInterval) {
        clearInterval(trackingInterval);
    }
    trackingInterval = setInterval(updateUavUgvPos, api_timeout);
    if (videoInterval) {
        clearInterval(videoInterval);
    }
    videoInterval = setInterval(fetchPhotos, video_timeout);
    alwwaysDisplayRealtime();
    alert("Origin fetched successfully! 🛫");
}

// Start tracking and update positions
function startTracking() {
    if(has_init){
        // Ensure tracking is not set twice
        // if (ugv_trackingInterval) {
        //     clearInterval(ugv_trackingInterval);
        // }
        // if (uav_trackingInterval) {
        //     clearInterval(uav_trackingInterval);
        // }
        // uav_trackingInterval = setInterval(updateUAVMarkerPosition, 500); // Request every 0.5 seconds
        // ugv_trackingInterval = setInterval(updateUGVMarkerPosition, 500); // Request every 0.5 seconds
        if (trackingInterval) {
            clearInterval(trackingInterval);
        }
        trackingInterval = setInterval(updateUavUgvPos, api_timeout);
        alert("Start updating position 🏃");
    }
    else{
        alert("Origin not available, refresh origin first 🤯");
    }
}

// Stop tracking positions
function stopTracking() {
    if(has_init){
        // if (ugv_trackingInterval) {
        //     clearInterval(ugv_trackingInterval);
        //     ugv_trackingInterval = null;
        // }
        // if (uav_trackingInterval) {
        //     clearInterval(uav_trackingInterval);
        //     uav_trackingInterval = null;
        // }
        if (trackingInterval) {
            clearInterval(trackingInterval);
            trackingInterval = null;
        }
        alert("Stop updating position 💺");
    }
    else{
        alert("Origin not available, refresh origin first 🤯");
    }   
}

async function stop_display(){
    endDataFilling();
    if (trackingInterval) {
        clearInterval(trackingInterval);
        trackingInterval = null;
    }
    if (videoInterval) {
        clearInterval(videoInterval);
        videoInterval = null;
    }
    ugv_marker.hide();
    ugvway = [];
    ugv_passedPolyline.hide();
    uav_marker.hide();
    uavway = [];
    uav_passedPolyline.hide();
    home_marker.hide();
    has_init = false
    has_depart = false;
    var re = await cleanData();
    if (!re){
        alert("Failed to clear data, retry later! 🤮");
        return;
    }
    alert("Data cleared successfully! 👌");
}


async function setDepart(){
    if(has_init){
        if (! has_depart){
           const flag = await fetchDepart();
           if(flag){
                has_depart = true;
                alert('Takeoff succeeded 😀'); 
           }
           else{
                alert('Takeoff failed 🤯');
           }
        }
        else{
            alert("Already airborne 👻");
        }
    }
    else{
        alert("Origin not available, refresh origin first 🤯");
    }
}

async function setLand(){
    if(has_init){
        if (has_depart){
           const flag = await fetchLand();
           if(flag){
                has_depart = false;
                alert('Landing succeeded 😀'); 
           }
           else{
                alert('Landing failed 🤯');
           }
        }
        else{
            alert("Returning 👻");
        }
    }
    else{
        alert("Origin not available, refresh origin first 🤯");
    }
}
