let update_span_interval = null;

async function updateUgvHeightSpan(){
    const ugv_h = await fetchUGVheight();
    if(ugv_h.length == 0){
        console.error("set ugv height span failed");
        return;
    }
    document.getElementById("agent2-time").innerText = Math.round(ugv_h[1]);
    document.getElementById("agent2-height").innerText = Math.round(ugv_h[0]);
}

async function updateUavHeightSpan(){
    const uav_h = await fetchUAVheight();
    if(uav_h.length == 0){
        console.error("set uav height span failed");
        return;
    }
    document.getElementById("agent1-time").innerText = Math.round(uav_h[1]);
    document.getElementById("agent1-height").innerText = Math.round(uav_h[0]);
}

async function updateUgvYawSpan(){
    const ugv_yaw = await fetchUGVyaw();
    if(ugv_yaw == null){
        console.error("set ugv yaw span failed");
        return;
    }
    document.getElementById("agent2-heading").innerText = Math.round(ugv_yaw);
}

async function updateUavYawSpan(){
    const uav_yaw = await fetchUAVyaw();
    if(uav_yaw == null){
        console.error("set uav yaw span failed");
        return;
    }
    document.getElementById("agent1-heading").innerText = Math.round(uav_yaw);
}

async function updateDistanceSpan(){
    const d = await fetchDistance();
    if(d == null){
        console.error("set distance span failed");
        return;
    }
    document.getElementById("distance").innerText = Math.round(d);
}

async function setOriginTime(time_str){
    document.getElementById("origin").innerText = time_str;
}

async function updateDHspan(){
    const d = await checkDH();
    if(d == null){
        console.error("set DH span failed");
        return;
    }
    document.getElementById("D-H").innerText = `${Math.round(d.D)}-${Math.round(d.H)}`;
}

async function setRunDistanceSpan(d){
    document.getElementById("run_distance").innerText = Math.round(d);
}

function startDataFilling(){
    // const funlist = [
    //     updateUgvHeightSpan, updateUavHeightSpan, updateUgvYawSpan,
    //     updateUavYawSpan, updateDistanceSpan, updateDHspan
    // ];
    // for (const f of funlist){
    //     update_span_interval.push(setInterval(f, 100));
    // }
    if (update_span_interval){
        clearInterval(update_span_interval);
    }
    update_span_interval = setInterval(setAllSpan, 100);
}


async function setAllSpan(){
    const data = await fetchSystemData();
    if (data != null){
        document.getElementById("D-H").innerText = `${data.D == null? '-':Math.round(data.D)} - ${data.H == null? '-':Math.round(data.H)}` ;
        document.getElementById("distance").innerText = data.distance == null ?'-': Math.round(data.distance);
        document.getElementById("agent1-title").innerText = `UAV🚁${data.depart != null && data.depart?'🛫': '🛬'}`;
        document.getElementById("agent1-heading").innerText = data.uav_yaw == null ?'-': Math.round(data.uav_yaw);
        document.getElementById("agent2-heading").innerText = data.ugv_yaw == null ?'-': - Math.round(data.ugv_yaw);
        document.getElementById("agent1-time").innerText = data.uav_t == null ?'-': data.uav_t.toFixed(1);
        document.getElementById("agent1-height").innerText = data.uav_h == null ?'-': Math.round(data.uav_h);
        document.getElementById("agent2-time").innerText = data.ugv_t == null ?'-': data.ugv_t.toFixed(1);
        document.getElementById("agent2-height").innerText = data.ugv_h == null ?'-': Math.round(data.ugv_h);
    }
}


function endDataFilling(){
    if (update_span_interval){
        clearInterval(update_span_interval);
    }
    update_span_interval = null;
    document.getElementById("D-H").innerText = `-`;
    document.getElementById("run_distance").innerText = '-';
    document.getElementById("origin").innerText = '-';
    document.getElementById("distance").innerText = '-';
    document.getElementById("agent1-heading").innerText = '-';
    document.getElementById("agent2-heading").innerText = '-';
    document.getElementById("agent1-time").innerText = '-';
    document.getElementById("agent1-height").innerText = '-';
    document.getElementById("agent2-time").innerText = '-';
    document.getElementById("agent2-height").innerText = '-';
    update_span_interval = [];
}