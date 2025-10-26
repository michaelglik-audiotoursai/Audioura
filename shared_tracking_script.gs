function doPost(e) {
  // Parse the incoming data
  let data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      'status': 'error',
      'message': 'Invalid JSON'
    })).setMimeType(ContentService.MimeType.JSON);
  }
  
  try {
    // Open the spreadsheet by ID
    const spreadsheet = SpreadsheetApp.openById(data.sheetId);
    
    let sheet;
    if (data.useTabs) {
      // Use separate tabs for each tour
      sheet = spreadsheet.getSheetByName(data.sheetName);
      if (!sheet) {
        // Create new sheet if it doesn't exist
        sheet = spreadsheet.insertSheet(data.sheetName);
        // Add headers
        sheet.getRange(1, 1, 1, 9).setValues([[
          'Timestamp', 'Tour Name', 'Tour Directory', 'User Name', 'Event', 
          'User Agent', 'Screen Size', 'URL', 'Tour ID'
        ]]);
      }
    } else {
      // Use single sheet for all tours
      sheet = spreadsheet.getSheetByName('AllTours');
      if (!sheet) {
        // Create AllTours sheet if it doesn't exist
        sheet = spreadsheet.insertSheet('AllTours');
        // Add headers
        sheet.getRange(1, 1, 1, 9).setValues([[
          'Timestamp', 'Tour Name', 'Tour Directory', 'User Name', 'Event', 
          'User Agent', 'Screen Size', 'URL', 'Tour ID'
        ]]);
      }
    }
    
    // Add the data
    sheet.appendRow([
      data.timestamp,
      data.tourName || '',
      data.tourDirectory || '',
      data.userName || 'Anonymous',
      data.event || '',
      data.userAgent || '',
      data.screenSize || '',
      data.url || '',
      data.tourId || ''
    ]);
    
    return ContentService.createTextOutput(JSON.stringify({
      'status': 'success'
    })).setMimeType(ContentService.MimeType.JSON);
    
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      'status': 'error',
      'message': error.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService.createTextOutput(JSON.stringify({
    'status': 'ready',
    'message': 'Tracking endpoint is active'
  })).setMimeType(ContentService.MimeType.JSON);
}
