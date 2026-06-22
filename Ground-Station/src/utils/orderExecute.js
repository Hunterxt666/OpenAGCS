// Apply threshold setting
function executeThreshold() {
    const thresholdValue = Number(document.getElementById('threshold').value);
    const flag = setth(thresholdValue);
    if(flag){
        alert('Threshold set successfully! 😊');
    }
    else{
        alert('Failed to set threshold! 🤯');
    }
}

// Apply D-H setting
function executeDH() {
    const dValue = document.getElementById('d-input').value;
    const hValue = document.getElementById('h-input').value;
    
    if (dValue === '' || hValue === ''){
        alert('Failed to set D/H: empty value! 🤯');
        return
    }
    flag = setDH(Number(dValue), Number(hValue));
    if(flag){
        alert('D/H set successfully! 😀');
    }
    else{
        alert('Failed to set D/H! 🤯');
    }
}
