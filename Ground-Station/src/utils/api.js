// API helpers for the operator interface described in the paper.
let api_config = {};  // Config object
let configLoadPromise = null;
let amapSdkPromise = null;

// Load config file async
async function loadConfig() {
    try {
        const response = await fetch('./src/config/api_config.json'); 
        if (!response.ok) {
            throw new Error(`Failed to load config file: ${response.status}`);
        }
        api_config = await response.json();
        console.log('Configuration loaded:', api_config);
    } catch (error) {
        console.error('Error loading config:', error);
        throw error;
    }
}

function ensureConfigLoaded() {
    if (!configLoadPromise) {
        configLoadPromise = loadConfig();
    }
    return configLoadPromise;
}

function loadAmapSdk() {
    if (window.AMap) {
        return Promise.resolve(window.AMap);
    }
    if (!amapSdkPromise) {
        amapSdkPromise = ensureConfigLoaded().then(() => {
            if (!api_config.amapKey || api_config.amapKey === 'YOUR_AMAP_KEY') {
                throw new Error('AMap key is not configured in src/config/api_config.json');
            }
            return new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(api_config.amapKey)}`;
                script.async = true;
                script.onload = () => resolve(window.AMap);
                script.onerror = () => reject(new Error('Failed to load AMap SDK'));
                document.head.appendChild(script);
            });
        });
    }
    return amapSdkPromise;
}


const timeoutFetch = (url, options = {}, timeout = 5000) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
  
        // Merge options and include AbortController signal
    const config = {
      ...options,
      signal: controller.signal
    };
  
    return fetch(url, config)
            .finally(() => clearTimeout(timeoutId))  // Clear timeout
      .catch((error) => {
        if (error.name === 'AbortError') {
          return Promise.reject(new Error('Request timed out'));
        }
        return Promise.reject(error);
      });
  };
  


// Fetch map center
async function fetchCenter() {
    try {
        const response = await timeoutFetch(
            url = `${api_config.apiBaseUrl}originPos`,
            options= {method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) {
            const data = await response.json();
            if (data.detail){
                alert(`${data.detail}🙃`)
            }
            throw new Error(`HTTP error !tt status: ${response.status}`);
        }
        const data = await response.json();
        console.info(`Center request result ${data.longitude}, ${data.latitude}`)
        return [wgs84ToGcj02(data.longitude, data.latitude), data.time] || [];
    } catch (error) {
        console.error("Failed to fetch center:", error);
        return [];
    }
}

// Request takeoff
async function fetchDepart() {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}setDepart`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        console.info(`Takeoff request result ${data}`)
        return true || false;
    } catch (error) {
        console.error("Failed to depart:", error);
        return false;
    }
}


// Request landing
async function fetchLand() {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}setLand`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        console.info(`Landing request result ${data}`)
        return true || false;
    } catch (error) {
        console.error("Failed to land:", error);
        return false;
    }
}


// Fetch new UGV position
async function fetchUGVpos() {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}ugvPos`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        return [wgs84ToGcj02(data.longitude, data.latitude), data.time] || [];
    } catch (error) {
        console.error("Failed to fetch ugv new position:", error);
        return [];
    }
}


// Fetch new UAV position
async function fetchUAVpos() {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}uavPos`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        return [wgs84ToGcj02(data.longitude, data.latitude), data.time] || [];
    } catch (error) {
        console.error("Failed to fetch uav new position:", error);
        return [];
    }
}

async function cleanData() {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}cleanTimeStr`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        return true;
    } catch (error) {
        console.error("Failed to clean time str:", error);
        return false;
    }
}

// Fetch new UGV height
async function fetchUGVheight() {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}ugvHeight`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        return [data.height, data.time] || [];
    } catch (error) {
        console.error("Failed to fetch ugv new height:", error);
        return [];
    }
}


// Fetch new UAV height
async function fetchUAVheight() {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}uavHeight`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        return [data.height, data.time] || [];
    } catch (error) {
        console.error("Failed to fetch uav new height:", error);
        return [];
    }
}


// Set DH
async function setDH(D, H) {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}setDH?D=${D}&H=${H}`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        return true;
    } catch (error) {
        console.error("Failed to set DH:", error);
        return false;
    }
}

// Check DH
async function checkDH() {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}checkDH`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        return data || null;
    } catch (error) {
        console.error("Failed to set DH:", error);
        return null;
    }
}

// Set threshold
async function setth(th) {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}setThreshold?threshold=${th}`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        return true;
    } catch (error) {
        console.error("Failed to set DH:", error);
        return false;
    }
}

// Fetch new UGV heading
async function fetchUGVyaw() {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}ugvOrientation`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        return data.ugv_orientation || null;
    } catch (error) {
        console.error("Failed to fetch ugv new Orientation:", error);
        return null;
    }
}


// Fetch new UAV heading
async function fetchUAVyaw() {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}uavOrientation`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        return data.uav_orientation || null;
    } catch (error) {
        console.error("Failed to fetch uav new Orientation:", error);
        return null;
    }
}

// Fetch distance
async function fetchDistance() {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}getDistance`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        return data.distance || null;
    } catch (error) {
        console.error("Failed to fetch distance:", error);
        return null;
    }
}


// Fetch system data
async function fetchSystemData() {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}systemData`,
            options={method: 'GET'},
            timeout=api_config.timeout
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        return data || null;
    } catch (error) {
        console.error("Failed to fetch SystemData:", error);
        return null;
    }
}


// Fetch system position
async function fetchSystemPos() {
    try {
        const response = await timeoutFetch(
            url=`${api_config.apiBaseUrl}systemPos`,
            options={method: 'GET'},
            timeout=api_config.timeout, 
        );
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        return data || null;
    } catch (error) {
        console.error("Failed to fetch SystemPos:", error);
        return null;
    }
}


function fetchPhotos() {
    const urls = [
        `${api_config.apiBaseUrl}ugvLatestPhoto`,  // Replace with actual endpoint 1
        `${api_config.apiBaseUrl}uavLatestPhoto`   // Replace with actual endpoint 2
    ];

    // Local fallback image path
    const localImages = "assets/no_image.png";

    urls.forEach((url, index) => {
        timeoutFetch(url=url, timeout=api_config.photo_timeout)
            .then(response => {
                if (response.status != 200) {
                    // If response is 404, use local image
                    return localImages;
                } else if (!response.ok) {
                    // For other errors, throw
                    throw new Error('Network response was not ok');
                }
                return response.blob();
            })
            .then(data => {
                const imgElement = document.getElementById(`photo${index}`);
                if (imgElement) {
                    // Check return data type
                    if (typeof data === 'string') {
                        // If data is string, it's a local image path
                        imgElement.src = data;
                    } else {
                        // If data is blob, it's from fetch
                        const imgUrl = URL.createObjectURL(data);
                        // Revoke old URL to avoid leaks
                        if (imgElement.src) {
                            URL.revokeObjectURL(imgElement.src);
                        }
                        // Update image src
                        imgElement.src = imgUrl;
                    }
                }
            })
            .catch(error => console.error('Error fetching photo:', error));
    });
}
