        document.addEventListener("DOMContentLoaded", function() {
            const stationDataContainer = document.getElementById('stationDataContainer');
            const loadingSpinner = document.getElementById('loadingSpinner');
            const progressDiv = document.getElementById('progress');
            const validTablesCountDiv = document.getElementById('validTablesCount');
            const invalidTablesCountDiv = document.getElementById('invalidTablesCount');
            const timerDiv = document.getElementById('timer');
            let validTablesCount = 0;
            let invalidTablesCount = 0;
            let startTime = Date.now();
            let timer;
            let map;
            let groups = {};
            let markers = {};

            let invalidTables = [];
            let tablesWithCoordinates = [];
            let completedTablesCount = 0;

            updateInformationContent(); 

            // Simplified data for CSV download purposes
    let invalidTablesForDownload = []; // This will hold data similar to 'invalidTables'
    let tablesWithCoordinatesForDownload = []; // This will hold data similar to 'tablesWithCoordinates'

        // Example function to update the arrays for download (you might already be updating these arrays elsewhere in your code)
        function updateDownloadData() {
        // Assuming 'invalidTables' and 'tablesWithCoordinates' are updated elsewhere,
        // copy their contents to the download-specific arrays here
        invalidTablesForDownload = [...invalidTables];
        tablesWithCoordinatesForDownload = [...tablesWithCoordinates];
    }

    // Function to convert an array of strings into a CSV string
    function arrayToCSV(array) {
        return array.map(item => `"${item}"`).join('\n');
    }

    // Function to trigger a download of text content as a file
    function downloadCSV(csvContent, filename) {
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const downloadLink = document.createElement('a');
        downloadLink.href = url;
        downloadLink.setAttribute('download', filename);
        document.body.appendChild(downloadLink); // Required for Firefox
        downloadLink.click();
        document.body.removeChild(downloadLink);
    }

    // Event listeners for the download buttons
    document.getElementById("downloadInvalidTables").addEventListener("click", function() {
        updateDownloadData(); // Ensure the latest data is in the download arrays
        const csvContent = arrayToCSV(invalidTablesForDownload);
        downloadCSV(csvContent, "invalidTables.csv");
    });

    document.getElementById("downloadTablesWithCoordinates").addEventListener("click", function() {
        updateDownloadData(); // Ensure the latest data is in the download arrays
        const csvContent = arrayToCSV(tablesWithCoordinatesForDownload);
        downloadCSV(csvContent, "tablesWithCoordinates.csv");
    });


    const menuItems = document.querySelectorAll('.vertical-menu a');

    menuItems.forEach(item => {
    item.addEventListener('click', function(event) {
        // Prevent default link behavior
        event.preventDefault();

        // Remove 'active-menu-item' class from all items
        menuItems.forEach(menuItem => menuItem.classList.remove('active-menu-item'));

        // Add 'active-menu-item' class to clicked item
        this.classList.add('active-menu-item');

        // Load corresponding content for clicked item
        if (this.id === 'linkAccordion') {
            // Load content for 'Manage Stations'
            loadContent('Accordion');
        } else if (this.id === 'linkInformation') {
            // Load content for 'Map Legend'
            updateInformationContent();
        }
    });
});

    


            const initialize = () => {
                startTime = Date.now();
                timer = setInterval(updateTimer, 1000);
                fetchTableNames();
                initMap();
            };


            function formatTimestamp(timestamp) {
                const date = new Date(timestamp);
                const year = date.getFullYear();
                const month = date.getMonth() + 1; // getMonth() returns month from 0-11
                const day = date.getDate();
                const hour = date.getHours();
                const minutes = date.getMinutes();
                return `${year}/${month.toString().padStart(2, '0')}/${day.toString().padStart(2, '0')} ${hour.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
            }


            const initMap = () => {
                map = new google.maps.Map(document.getElementById('map'), {
                    center: {lat: 9.1021, lng: 18.2812}, // Centered on Africa
                    zoom: 4, // Adjusted zoom level to fit Africa within the viewport
                    minZoom: 3, // Minimum zoom level allowed
                    maxZoom: 17 // Maximum zoom level allowed
                });
            };

            const updateTimer = () => {
                const elapsed = Math.floor((Date.now() - startTime) / 1000);
                timerDiv.innerText = `Time elapsed: ${elapsed} seconds`;
            };

            const fetchTableNames = async () => {
                try {
                    const response = await fetch('/get_all_tables');
                    const data = await response.json();
                    const tables = data.tables;
                    progressDiv.innerText = `Progress: 0/${tables.length} (0%)`;
                    fetchTableData(tables);
                } catch (error) {
                    console.error('Error fetching tables:', error);
                }
            };

            const fetchTableData = async (tables) => {
                const fetchPromises = tables.map((table, index) => fetch(`/combined_data/${table}`)
                    .then(response => response.json())
                    .then(data => processTableData(data, table, tables.length))
                    .catch(error => {
                        console.error('Error fetching table data:', error);
                        invalidTablesCount++;
                        updateUI(tables.length);
                        return null;
                    })
                );
                const stationData = (await Promise.all(fetchPromises)).filter(data => data !== null);
                finalize(stationData);

                
            };

            const processTableData = (data, table, totalTables) => {
    if (!data.error && data.data) {
        const { relational_data, timestream_data } = data.data;
        const timestamp = timestream_data.length > 0 ? timestream_data[0][3] : null;
        const timestreamMap = timestream_data.reduce((acc, curr) => {
            acc[curr[2]] = curr[4];
            return acc;
        }, {});

        const station = {
            stationName: table,
            timestamp: timestamp,
            topicID: relational_data.topic_id,
            groupName: relational_data.group_name,
            userName: relational_data.user_info.map(user => user.user_name).join(', '),
            longitude: parseFloat(timestreamMap['Longitude']) || parseFloat(relational_data.longitude),
            latitude: parseFloat(timestreamMap['Latitude']) || parseFloat(relational_data.latitude),
            sensorData: {
                BP: timestreamMap['BP'] || null,
                RH: timestreamMap['RH'] || null,
                Rain_hr: timestreamMap['Rain_hr'] || null,
                Solar_hr: timestreamMap['Solar_hr'] || null,
                WSpeed: timestreamMap['WSpeed'] || null,
            }
        };

        if (station.latitude && station.longitude) {
            // This table has valid coordinates
            tablesWithCoordinates.push(table);
        }

        // Process valid data, add markers, etc.
        const marker = addMarker(station);
        addToAccordion(station, marker);

        validTablesCount++;
    } else {
        // Data is invalid or couldn't be processed
        invalidTables.push(table); // Add table to invalidTables list
        invalidTablesCount++;
    }

    // Update UI regardless of whether the table is valid or invalid
    updateUI(totalTables);
};

            

            const addMarker = (station) => {
    if (station.latitude && station.longitude) {
        // Default color for missing sensor data
        let color = 'purple';

        // Check if any sensor data is missing
        const hasMissingSensorData = Object.values(station.sensorData).some(data => data === null);

        // Determine color based on timestamp if no sensor data is missing
        if (!hasMissingSensorData) {
            if (station.timestamp) {
                const timestampAgeHours = (Date.now() - new Date(station.timestamp).getTime()) / (1000 * 60 * 60);
                if (timestampAgeHours < 6) {
                    color = 'green';
                } else if (timestampAgeHours >= 6 && timestampAgeHours < 12) {
                    color = 'orange';
                } else if (timestampAgeHours >= 12 && timestampAgeHours <= 24) {
                    color = 'red';
                } else {
                    color = 'black'; // Color for timestamps older than 24 hours
                }
            } else {
                color = 'purple'; // Default color if timestamp is invalid
            }
        }

        // Define a circle symbol with the determined color
        const circleSymbol = {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 8, // Size of the circle
            fillColor: color,
            fillOpacity: 1,
            strokeColor: 'white',
            strokeWeight: 2
        };

        const marker = new google.maps.Marker({
            position: new google.maps.LatLng(station.latitude, station.longitude),
            map: map,
            title: station.stationName, // You might keep this for basic hover text
            icon: circleSymbol,
            visible: true
        });

        const formattedTimestamp = station.timestamp ? formatTimestamp(station.timestamp) : 'No valid timestamp';
            

        // Prepare content for the InfoWindow
        const sensorDataContent = Object.entries(station.sensorData)
            .map(([key, value]) => `${key}: ${value}`)
            .join('<br>');

        const infoWindowContent = `
            <div>
                <strong>${station.stationName}</strong><br>
                Timestamp: ${formattedTimestamp}<br>
                ${sensorDataContent}
            </div>
        `;

        // Create an InfoWindow
        const infoWindow = new google.maps.InfoWindow({
            content: infoWindowContent
        });

        // Add listener to open InfoWindow on marker hover
        marker.addListener('mouseover', () => {
            infoWindow.open({
                anchor: marker,
                map,
                shouldFocus: false
            });
        });

        // Add listener to close InfoWindow when not hovering
        marker.addListener('mouseout', () => {
            infoWindow.close();
        });

        marker.addListener('click', () => {
            // Assuming station.topic_id is available and contains the relevant topic ID
            // Replace 'station.topic_id' with the correct property path if it's different
            const topicID = station.topicID; // Make sure this is the correct way to access your topic ID
            const targetUrl = `/topic/${topicID}`;
            window.open(targetUrl, '_blank'); // Redirect the user to the target URL
        });

        markers[station.stationName] = marker;
        return marker;
    }
    return null;
};

const sidebarContent = document.getElementById('sidebarContent');

document.getElementById('linkAccordion').addEventListener('click', function(e) {
    e.preventDefault();
    loadContent('Accordion'); // Assuming 'Accordion' refers to specific content or functionality you want to load.
});

document.getElementById('linkInformation').addEventListener('click', function(e) {
    e.preventDefault();
    loadContent('Information'); // Assuming 'Information' refers to specific content or functionality you want to load.
});


function loadContent(contentType) {
    const sidebarContent = document.getElementById('sidebarContent');
    sidebarContent.innerHTML = ''; // Clear existing content

    if (contentType === 'Accordion') {
        // Check if the accordion already exists or needs to be generated
        const existingAccordion = document.getElementById('stationAccordion');
        if (!existingAccordion) {
            createAccordion();
        } else {
            // If it exists, simply display it
            existingAccordion.style.display = '';
        }
    } else if (contentType === 'Information') {
        // Load the specific content for 'Information'
        const informationHtml = `
        <p>Progress: ${progress}</p>
        <p>Valid tables: ${validTablesCount}</p>
        <p>Invalid tables: ${invalidTablesCount}</p>
        <p>Time elapsed: ${elapsedTime} seconds</p>
        `;
        sidebarContent.innerHTML = informationHtml;
    } 
}


// This example assumes you have a way to hide the accordion initially or after showing other content
function toggleAccordionVisibility() {
    const accordion = document.getElementById('stationAccordion');
    if (accordion) {
        accordion.style.display = accordion.style.display === 'none' ? '' : 'none';
    }
}




// New function to fit map bounds to markers
const fitMapToBounds = () => {
    const bounds = new google.maps.LatLngBounds();
    Object.values(markers).forEach(marker => {
        if (marker && marker.getPosition) {
            bounds.extend(marker.getPosition());
        }
    });
    
    // Check if bounds have markers, then fit the map to these bounds
    if (!bounds.isEmpty()) {
        map.fitBounds(bounds);
    }
};

google.maps.event.addDomListener(window, 'load', initMap);

            const addToAccordion = (station, marker) => {
                const groupName = station.groupName || 'Unassigned';
                if (!groups[groupName]) {
                    groups[groupName] = {
                        stations: [],
                        markers: []
                    };
                }
                groups[groupName].stations.push(station.stationName);
                if (marker) {
                    groups[groupName].markers.push(marker);
                }
            };

            const updateUI = (totalTables) => {
                completedTablesCount++;
                const progress = completedTablesCount / totalTables;
                const percent = (progress * 100).toFixed(2);
                progressDiv.innerText = `Progress: ${completedTablesCount}/${totalTables} (${percent}%)`;
                validTablesCountDiv.innerText = `Valid tables: ${validTablesCount}`;
                invalidTablesCountDiv.innerText = `Invalid tables: ${invalidTablesCount}`;
                if (completedTablesCount === totalTables) {
                    createAccordion();
                }

                if (completedTablesCount === totalTables) {
                                updateModalLists();
                            }
            };

            

const updateModalLists = () => {
    const invalidTablesList = document.getElementById('invalidTablesList');
    const tablesCoordinatesList = document.getElementById('tablesCoordinatesList');

    // Clear previous entries
    invalidTablesList.innerHTML = '';
    tablesCoordinatesList.innerHTML = '';

    // Populate invalid tables list
    invalidTables.forEach(table => {
        const li = document.createElement('li');
        li.className = 'list-group-item';
        li.textContent = table;
        invalidTablesList.appendChild(li);
    });

    // Populate tables with coordinates list
    tablesWithCoordinates.forEach(table => {
        const li = document.createElement('li');
        li.className = 'list-group-item';
        li.textContent = table;
        tablesCoordinatesList.appendChild(li);
    });
};

function updateInformationContent() {
    // Update variables here or ensure they're updated before calling this function
    const informationHtml = `
    <hr><h5>Data Received</h5>
                    <div class="legend-item">
                        <div class="legend-color" style="background-color: green;"></div> Within the last 6 hours
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background-color: rgb(255, 148, 18);"></div>Between 6 and 12 hours ago.
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background-color: red;"></div>Between 12 and 24 hours ago.
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background-color: black;"></div> More than 24 hours ago.
                    </div><hr>
                    <div class="legend-item">
                        <div class="legend-color" style="background-color: purple;"></div> Stations not receiving data.
                    </div><hr>
    `;
    const sidebarContent = document.getElementById('sidebarContent');
    if (sidebarContent) {
        sidebarContent.innerHTML = informationHtml;
    } else {
        console.error('sidebarContent element not found');
    }
}



// Example of how you might call this function
document.getElementById('linkInformation').addEventListener('click', function(e) {
    e.preventDefault();
    updateInformationContent(); // Call this function to update the content dynamically
});


function downloadArrayAsCSV(array, filename) {
    // Convert the array into a CSV string
    const csvContent = array.map(e => `"${e}"`).join('\n');

    // Create a Blob with the CSV content
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });

    // Create a temporary download link
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", filename);

    // Append the link to the body, trigger click to download, and then remove the link
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

document.addEventListener("DOMContentLoaded", function() {
    // Add event listener for the "Download Invalid Tables" button
    document.getElementById("downloadInvalidTables").addEventListener("click", function() {
        downloadArrayAsCSV(invalidTables, "invalidTables.csv");
    });

    // Add event listener for the "Download Tables With Coordinates" button
    document.getElementById("downloadTablesWithCoordinates").addEventListener("click", function() {
        downloadArrayAsCSV(tablesWithCoordinates, "tablesWithCoordinates.csv");
    });
});








const createAccordion = () => {
        const sidebarContent = document.getElementById('sidebarContent');
        sidebarContent.innerHTML = '<div class="accordion" id="stationAccordion"></div>';
        const accordion = document.getElementById('stationAccordion');

        Object.keys(groups).forEach((groupName, index) => {
            // Start with the accordion collapsed by setting aria-expanded to false and removing show class
            const groupHtml = `
                <div class="card">
                    <div class="card-header" id="heading${index}">
                        <h2 class="mb-0">
                            <button class="btn btn-link collapsed" type="button" data-toggle="collapse" data-target="#collapse${index}" aria-expanded="false" aria-controls="collapse${index}">
                                ${groupName}
                            </button>
                        </h2>
                    </div>
                    <div id="collapse${index}" class="collapse" aria-labelledby="heading${index}" data-parent="#stationAccordion">
                        <div class="card-body">
                            <input type="checkbox" class="group-checkbox" data-group="${groupName}" checked> Toggle All<br>
                            ${groups[groupName].stations.map(stationName => {
                                // Assuming 'groups' structure is adjusted to include user names in each station object
                                const station = groups[groupName].stations.find(s => s.stationName === stationName);
                                const userNames = station && station.userName ? station.userName : 'Unassigned user';
                                return `
                                    <div>
                                        <input type="checkbox" class="station-checkbox" data-station="${stationName}" data-group="${groupName}" checked> 
                                        ${stationName} - users: ${userNames}
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    </div>
                </div>
            `;
            accordion.innerHTML += groupHtml;
        });

        document.querySelectorAll('.group-checkbox').forEach(groupCheckbox => {
            groupCheckbox.addEventListener('change', function() {
                const groupName = this.getAttribute('data-group');
                const isChecked = this.checked;
                document.querySelectorAll(`.station-checkbox[data-group="${groupName}"]`).forEach(stationCheckbox => {
                    stationCheckbox.checked = isChecked;
                    // Toggle marker visibility for each station
                    const stationName = stationCheckbox.getAttribute('data-station');
                    if(markers[stationName]) {
                        markers[stationName].setVisible(isChecked);
                    }
                });
            });
        });

        document.querySelectorAll('.station-checkbox').forEach(stationCheckbox => {
            stationCheckbox.addEventListener('change', function() {
                const stationName = this.getAttribute('data-station');
                const isChecked = this.checked;
                if(markers[stationName]) {
                    markers[stationName].setVisible(isChecked);
                }
            });
        });



            };

            const finalize = (stationData) => {
    clearInterval(timer); // Stop the timer
    loadingSpinner.style.display = 'none';
    updateModalLists(); // Populate the modal with the lists
    fitMapToBounds(); // Adjust map view
};



            initialize();
            
        });

    

    
    