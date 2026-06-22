// map.js
// Coordinate conversion utilities
const pi = 3.14159265358979324;
const a = 6378245.0; // Semi-major axis
const ee = 0.00669342162296594323; // Flattening
function transformLat(x, y) {
    let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
    ret += (20.0 * Math.sin(6.0 * x * pi) + 20.0 * Math.sin(2.0 * x * pi)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(y * pi) + 40.0 * Math.sin(y / 3.0 * pi)) * 2.0 / 3.0;
    ret += (160.0 * Math.sin(y / 12.0 * pi) + 320 * Math.sin(y * pi / 30.0)) * 2.0 / 3.0;
    return ret;
}

function transformLon(x, y) {
    let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
    ret += (20.0 * Math.sin(6.0 * x * pi) + 20.0 * Math.sin(2.0 * x * pi)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(x * pi) + 40.0 * Math.sin(x / 3.0 * pi)) * 2.0 / 3.0;
    ret += (150.0 * Math.sin(x / 12.0 * pi) + 300.0 * Math.sin(x / 30.0 * pi)) * 2.0 / 3.0;
    return ret;
}

function wgs84ToGcj02(lon, lat) {
    if (outOfChina(lat, lon)) {
        return [lat, lon];
    }

    let dLat = transformLat(lon - 105.0, lat - 35.0);
    let dLon = transformLon(lon - 105.0, lat - 35.0);
    const radLat = lat / 180.0 * pi;
    let magic = Math.sin(radLat);
    magic = 1 - ee * magic * magic;
    const sqrtMagic = Math.sqrt(magic);
    dLat = (dLat * 180.0) / ((a * (1 - ee)) / (magic * sqrtMagic) * pi);
    dLon = (dLon * 180.0) / (a / sqrtMagic * Math.cos(radLat) * pi);
    const mgLat = lat + dLat;
    const mgLon = lon + dLon;
    return [mgLon, mgLat];
}

function outOfChina(lat, lon) {
    return lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271;
}

let map, ugv_marker, ugv_passedPolyline, uav_marker, uav_passedPolyline, home_marker;
let ugv_t, uav_t;
let origin_time;
let ugv_trackingInterval, uav_trackingInterval; // Stores interval IDs
let ugvway = [], uavway = [], pre_len=0;

// Initialize map
async function initializeMap() {
    // Use center point loaded from api.js
    map = new AMap.Map("container", {
        resizeEnable: true,
        center: [113.958553, 22.799473],
        zoom: 17,
        viewMode: '3D',
        terrain: true,
    });

    const caricon = new AMap.Icon({
        size: new AMap.Size(24, 24), // Set icon size, e.g. 32x32 px
        image: "assets/car.png", // Icon URL
        imageSize: new AMap.Size(24, 24) // Set actual icon size to keep scale correct
    });

    ugv_marker = new AMap.Marker({
        map: map,
        icon: caricon,
        offset: new AMap.Pixel(-12, -12),
        visible: false, // Hidden by default
    });
    const staricon = new AMap.Icon({
        size: new AMap.Size(20, 20), // Set icon size, e.g. 32x32 px
        image: "assets/star.png", // Icon URL
        imageSize: new AMap.Size(20, 20) // Set actual icon size to keep scale correct
    });

    home_marker = new AMap.Marker({
        map: map,
        icon: staricon,
        offset: new AMap.Pixel(-10, -10),
        visible: false, // Hidden by default
    });
    const droneicon = new AMap.Icon({
        size: new AMap.Size(20, 20), // Set icon size, e.g. 32x32 px
        image: "assets/drone.png", // Icon URL
        imageSize: new AMap.Size(20, 20) // Set actual icon size to keep scale correct
    });

    uav_marker = new AMap.Marker({
        map: map,
        icon: droneicon,
        offset: new AMap.Pixel(-10, -10),
        visible: false, // Hidden by default
    });

    ugv_passedPolyline = new AMap.Polyline({
        map: map,
        strokeColor: "#003366",
        strokeWeight: 3,
        showDir: true,
    });
    uav_passedPolyline = new AMap.Polyline({
        map: map,
        strokeColor: "#ffff4d",
        strokeWeight: 3,
        showDir: true,
    });
    // map.setFitView();
}

async function updateUGVMarkerPosition() {
    const new_pos = await fetchUGVpos();
    if (new_pos.length > 0) {
        ugv_marker.setPosition(new_pos[0]); // Update marker position
        map.setCenter(new_pos[0]);
        ugvway.push(new_pos[0]);
        ugv_passedPolyline.setPath(ugvway);
        ugv_passedPolyline.show();
        setRunDistanceSpan(ugv_passedPolyline.getLength());
        ugv_t = new_pos[1];
        console.log("UGV Marker moved to:", new_pos[0], "time, ", ugv_t);
    } else {
        console.error("Invalid position data from API");
    }
}

async function updateUAVMarkerPosition() {
    const new_pos = await fetchUAVpos();
    if (new_pos.length > 0) {
        uav_marker.setPosition(new_pos[0]); // Update marker position
        uavway.push(new_pos[0]);
        uav_passedPolyline.setPath(uavway);
        uav_passedPolyline.show();
        uav_t = new_pos[1];
        console.log("UAV Marker moved to:", new_pos[0], "time, ", uav_t);
    } else {
        console.error("Invalid position data from API");
    }
}

async function updateUavUgvPos(){
    const new_pos = await fetchSystemPos();
    if (new_pos) {
        if(new_pos.ugv_longitude != null && new_pos.ugv_latitude != null){
            const ugvpos = wgs84ToGcj02(new_pos.ugv_longitude, new_pos.ugv_latitude);
            if (ugvpos != null && ugvpos[0] != null && ugvpos[1] != null){
                ugvway.push(ugvpos);
                cur_len = ugv_passedPolyline.getLength();
                map.setCenter(ugvpos);
                ugv_marker.setPosition(ugvpos); // Update marker position
                ugv_passedPolyline.setPath(ugvway);
                ugv_passedPolyline.show();
                pre_len = cur_len;
                setRunDistanceSpan(cur_len);
                console.log("UGV Marker moved to:", ugvpos);
            }
        }
        if(new_pos.uav_longitude != null && new_pos.uav_latitude != null){
            const uavpos = wgs84ToGcj02(new_pos.uav_longitude, new_pos.uav_latitude);
            if (uavpos != null && uavpos[0] != null && uavpos[1] != null){
                uav_marker.setPosition(uavpos); // Update marker position
                uavway.push(uavpos);
                uav_passedPolyline.setPath(uavway);
                uav_passedPolyline.show();
                console.log("UAV Marker moved to:", uavpos);
            }
        }
    } else {
        console.error("Invalid position data from API");
    }
}
