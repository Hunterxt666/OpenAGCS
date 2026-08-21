// Apply threshold setting
async function executeThreshold() {
    const thresholdValue = Number(document.getElementById('threshold').value);
    if (!Number.isFinite(thresholdValue) || thresholdValue < 0) {
        alert('Failed to set threshold: enter a non-negative number! 🤯');
        return;
    }
    const flag = await setth(thresholdValue);
    if(flag){
        alert('Threshold set successfully! 😊');
    }
    else{
        alert('Failed to set threshold! 🤯');
    }
}

// Apply D-H setting
async function executeDH() {
    const dText = document.getElementById('d-input').value;
    const hText = document.getElementById('h-input').value;
    
    if (dText === '' || hText === ''){
        alert('Failed to set D/H: empty value! 🤯');
        return;
    }
    const dValue = Number(dText);
    const hValue = Number(hText);
    if (
        !Number.isFinite(dValue) ||
        !Number.isFinite(hValue) ||
        dValue < 0 ||
        dValue > 100 ||
        hValue <= 0 ||
        hValue > 120
    ) {
        alert('Failed to set D/H: require 0 ≤ D ≤ 100 m and 0 < H ≤ 120 m! 🤯');
        return;
    }

    const flag = await setDH(dValue, hValue);
    if(flag){
        alert('D/H set successfully! 😀');
    }
    else{
        alert('Failed to set D/H! 🤯');
    }
}
