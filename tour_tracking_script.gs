function doPost(e) {
  // Parse the incoming data
  let data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      'status': 'error',
      'message': 'Invalid JSON data'
    }));
  }
  
  // Add timestamp if not provided
  if (!data.timestamp) {
    data.timestamp = new Date().toISOString();
  }
  
  // Log to spreadsheet
  const spreadsheetId = ''; // Add your spreadsheet ID here
  const sheet = SpreadsheetApp.openById(spreadsheetId).getSheetByName('Usage') || 
                SpreadsheetApp.openById(spreadsheetId).getSheets()[0];
  
  // Check if headers exist, if not add them
  if (sheet.getLastRow() === 0) {
    sheet.appendRow([
      'Timestamp', 
      'Tour ID', 
      'Tour Name', 
      'User Name', 
      'Event', 
      'User Agent', 
      'Screen Size'
    ]);
  }
  
  // Append the data
  sheet.appendRow([
    data.timestamp,
    data.tourId,
    data.tourName,
    data.userName || 'Anonymous',
    data.event,
    data.userAgent,
    data.screenSize
  ]);
  
  // Return success
  return ContentService.createTextOutput(JSON.stringify({
    'status': 'success'
  }));
}

function doGet() {
  return HtmlService.createHtmlOutput(
    '<h1>Audio Tour Tracking Service</h1><p>This is a tracking endpoint for audio tours.</p>'
  );
}