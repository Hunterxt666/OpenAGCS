// main.js

async function main() {
    await ensureConfigLoaded();
    await loadAmapSdk();
    await initializeMap(); // Initialize map
    // setInterval(updatePath, 2000); // Periodically update path
}

// Start main program
main();
