// ============================================================
// GOOGLE APPS SCRIPT - Paste this in your Google Sheet
// Go to: Extensions → Apps Script → paste → Deploy → Web app
// Set "Who has access" to "Anyone"
// Copy the deployed URL and paste it in google_sheets_api.py
// ============================================================

// ==================== CONFIG ====================
// The "Users" sheet must be in THIS spreadsheet (the one with the script)
// Chit files must be Google Sheets inside a folder named "chitData" in your Drive

var CHIT_FOLDER_NAME = "chitData";

// ==================== SECURITY ====================
// Set your API key in Apps Script Project Settings:
// Go to: Project Settings (gear icon) → Script Properties → Add
// Property: API_KEY    Value: your_strong_secret_key
var API_KEY = PropertiesService.getScriptProperties().getProperty("API_KEY") || "";

// ==================== MAIN HANDLERS ====================

function doGet(e) {
  return handleRequest(e);
}

function doPost(e) {
  return handleRequest(e);
}

function handleRequest(e) {
  // Verify API key
  var key = e.parameter.key;
  if (key !== API_KEY) {
    return ContentService.createTextOutput(JSON.stringify({ error: "Unauthorized" }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  var action = e.parameter.action;
  var result;

  try {
    switch (action) {
      // ---- USER MANAGEMENT ----
      case "getUsers":
        result = handleGetUsers();
        break;
      case "addUser":
        result = handleAddUser(JSON.parse(e.postData.contents));
        break;
      case "deleteUser":
        result = handleDeleteUser(JSON.parse(e.postData.contents));
        break;
      case "updateUser":
        result = handleUpdateUser(JSON.parse(e.postData.contents));
        break;

      // ---- CHIT DATA ----
      case "getChitFolders":
        result = handleGetChitFolders();
        break;
      case "getChitFiles":
        result = handleGetChitFiles(e.parameter.folder);
        break;
      case "getMembers":
        result = handleGetMembers(e.parameter.file);
        break;
      case "getAllMembers":
        result = handleGetAllMembers(e.parameter.file);
        break;
      case "getChitNumber":
        result = handleGetChitNumber(e.parameter.file);
        break;
      case "updateCampaign":
        result = handleUpdateCampaign(e.parameter.file, JSON.parse(e.postData.contents));
        break;
      case "getReminderData":
        result = handleGetReminderData(e.parameter.file);
        break;
      case "getContactNumber":
        result = handleGetContactNumber(e.parameter.file);
        break;
      case "getAllChitData":
        result = handleGetAllChitData(e.parameter.file);
        break;
      case "getChitViewData":
        result = handleGetChitViewData(e.parameter.file);
        break;
      case "getAllFilesData":
        result = handleGetAllFilesData();
        break;
      case "updateMemberPayment":
        result = handleUpdateMemberPayment(e.parameter.file, JSON.parse(e.postData.contents));
        break;

      default:
        result = { error: "Unknown action: " + action };
    }
  } catch (err) {
    result = { error: err.message };
  }

  return ContentService.createTextOutput(JSON.stringify(result))
    .setMimeType(ContentService.MimeType.JSON);
}

// ==================== USER MANAGEMENT ====================

function handleGetUsers() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Users");
  if (!sheet) return [];
  var data = sheet.getDataRange().getValues();
  var users = [];
  for (var i = 1; i < data.length; i++) {
    if (data[i][0]) {
      users.push({
        username: String(data[i][0]),
        password: String(data[i][1]),
        role: String(data[i][2] || "user"),
        email: String(data[i][3] || ""),
        chitFile: String(data[i][4] || "")
      });
    }
  }
  return users;
}

function handleAddUser(p) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Users");
  if (!sheet) {
    sheet = SpreadsheetApp.getActiveSpreadsheet().insertSheet("Users");
    sheet.appendRow(["username", "password", "role", "email", "chitFile"]);
  }
  sheet.appendRow([p.username, p.password, p.role || "user", p.email || "", p.chitFile || ""]);
  return { success: true };
}

function handleDeleteUser(p) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Users");
  var data = sheet.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (String(data[i][0]) === p.username) {
      sheet.deleteRow(i + 1);
      return { success: true };
    }
  }
  return { success: false, error: "User not found" };
}

function handleUpdateUser(p) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Users");
  var data = sheet.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (String(data[i][0]) === p.username) {
      var row = i + 1;
      if (p.password) sheet.getRange(row, 2).setValue(p.password);
      if (p.role) sheet.getRange(row, 3).setValue(p.role);
      if (p.email !== undefined && p.email !== "") sheet.getRange(row, 4).setValue(p.email);
      if (p.chitFile !== undefined && p.chitFile !== "") sheet.getRange(row, 5).setValue(p.chitFile);
      return { success: true };
    }
  }
  return { success: false, error: "User not found" };
}

// ==================== CHIT FILE OPERATIONS ====================

function getChitDataFolder() {
  var folders = DriveApp.getFoldersByName(CHIT_FOLDER_NAME);
  if (folders.hasNext()) return folders.next();
  return null;
}

function getSpreadsheetByName(fileName) {
  var folder = getChitDataFolder();
  if (!folder) throw new Error("chitData folder not found in Google Drive");

  // Search in all subfolders
  var subFolders = folder.getFolders();
  while (subFolders.hasNext()) {
    var subFolder = subFolders.next();
    var files = subFolder.getFilesByName(fileName);
    while (files.hasNext()) {
      var file = files.next();
      var mime = file.getMimeType();
      if (mime === "application/vnd.google-apps.spreadsheet") {
        return SpreadsheetApp.open(file);
      }
      if (mime === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") {
        var converted = Drive.Files.copy(
          { title: file.getName(), parents: [{ id: subFolder.getId() }], mimeType: "application/vnd.google-apps.spreadsheet" },
          file.getId()
        );
        file.setTrashed(true);
        return SpreadsheetApp.openById(converted.id);
      }
    }

    // Try without extension
    var nameNoExt = fileName.replace(/\.xlsx$/i, "");
    files = subFolder.getFiles();
    while (files.hasNext()) {
      var file = files.next();
      var fName = file.getName().replace(/\.xlsx$/i, "");
      if (fName === nameNoExt) {
        var mime = file.getMimeType();
        if (mime === "application/vnd.google-apps.spreadsheet") {
          return SpreadsheetApp.open(file);
        }
      }
    }
  }

  // Also search in root chitData folder (backward compatibility)
  var files = folder.getFilesByName(fileName);
  while (files.hasNext()) {
    var file = files.next();
    var mime = file.getMimeType();
    if (mime === "application/vnd.google-apps.spreadsheet") {
      return SpreadsheetApp.open(file);
    }
  }

  throw new Error("File '" + fileName + "' not found in chitData folder or subfolders.");
}

function handleGetChitFolders() {
  var folder = getChitDataFolder();
  if (!folder) return [];
  var subFolders = folder.getFolders();
  var names = [];
  while (subFolders.hasNext()) {
    names.push(subFolders.next().getName());
  }
  return names.sort();
}

function handleGetChitFiles(folderName) {
  var folder = getChitDataFolder();
  if (!folder) return [];

  // If folder name provided, get files from that subfolder
  if (folderName) {
    var subFolders = folder.getFoldersByName(folderName);
    if (subFolders.hasNext()) {
      folder = subFolders.next();
    } else {
      return [];
    }
  }

  var files = folder.getFiles();
  var names = [];
  while (files.hasNext()) {
    var file = files.next();
    var mime = file.getMimeType();
    if (mime === "application/vnd.google-apps.spreadsheet" ||
        mime === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") {
      names.push(file.getName());
    }
  }
  return names;
}

function handleGetMembers(fileName) {
  var ss = getSpreadsheetByName(fileName);
  var sheet = ss.getSheetByName("chitMembers");
  if (!sheet) return [];
  var data = sheet.getDataRange().getValues();
  var headers = data[0];
  var nameIdx = headers.indexOf("Name");
  var mobileIdx = headers.indexOf("MobileNumber");
  var withdrawIdx = headers.indexOf("Withdraw");

  var members = [];
  for (var i = 1; i < data.length; i++) {
    var withdraw = withdrawIdx >= 0 ? String(data[i][withdrawIdx]).trim().toLowerCase() : "no";
    var name = data[i][nameIdx];
    if (withdraw !== "Yes" && name && String(name).trim()) {
      members.push({
        name: String(name).trim(),
        mobile: String(data[i][mobileIdx]).trim()
      });
    }
  }
  return members;
}

function handleGetAllMembers(fileName) {
  var ss = getSpreadsheetByName(fileName);
  var sheet = ss.getSheetByName("chitMembers");
  if (!sheet) return [];
  var data = sheet.getDataRange().getValues();
  var headers = data[0];
  var nameIdx = headers.indexOf("Name");
  var mobileIdx = headers.indexOf("MobileNumber");

  var members = [];
  for (var i = 1; i < data.length; i++) {
    var name = data[i][nameIdx];
    var mobile = data[i][mobileIdx];
    if (name && String(name).trim() && mobile) {
      members.push({
        name: String(name).trim(),
        mobile: String(mobile).trim()
      });
    }
  }
  return members;
}

function handleGetChitNumber(fileName) {
  var ss = getSpreadsheetByName(fileName);
  var sheet = ss.getSheetByName("chitNumberDetails");
  if (!sheet) return {};
  var data = sheet.getDataRange().getValues();
  var now = new Date();
  var chitNumber = "";
  var noCount = 0;
  var amountPerPerson = 0;
  var conductedStatus = "";

  for (var i = 1; i < data.length; i++) {
    var conducted = String(data[i][1]).trim().toLowerCase();
    if (conducted === "no") noCount++;
    var monthVal = data[i][2];
    if (monthVal instanceof Date) {
      if (monthVal.getMonth() === now.getMonth() && monthVal.getFullYear() === now.getFullYear()) {
        chitNumber = data[i][0];
        amountPerPerson = data[i][6] || 0;
        conductedStatus = conducted;
      }
    }
  }

  var totalAmount = 0, chitName = "", gpay = "", contactNumber = "", balanceChit = "";
  var detailsSheet = ss.getSheetByName("chitDetails");
  if (detailsSheet) {
    var dData = detailsSheet.getDataRange().getValues();
    var dHeaders = dData[0];
    if (dData.length > 1) {
      var row = dData[1];
      var idx;
      idx = dHeaders.indexOf("Chit Amount");
      if (idx >= 0) totalAmount = row[idx] || 0;
      idx = dHeaders.indexOf("Chit Name");
      if (idx >= 0) chitName = String(row[idx] || "");
      idx = dHeaders.indexOf("Gpay");
      if (idx >= 0) gpay = String(row[idx] || "");
      idx = dHeaders.indexOf("Contact Number");
      if (idx >= 0) contactNumber = String(row[idx] || "");
      idx = dHeaders.indexOf("Balance Chit");
      if (idx >= 0) balanceChit = row[idx];
    }
  }

  return {
    chitNumber: chitNumber,
    chitRemaining: noCount - 1,
    amountPerPerson: amountPerPerson,
    totalAmount: totalAmount,
    chitName: chitName,
    gpay: gpay,
    contactNumber: contactNumber,
    conducted: conductedStatus,
    balanceChit: balanceChit
  };
}

function handleUpdateCampaign(fileName, p) {
  var ss = getSpreadsheetByName(fileName);

  // Update chitNumberDetails
  var sheet = ss.getSheetByName("chitNumberDetails");
  var data = sheet.getDataRange().getValues();
  var now = new Date();
  for (var i = 1; i < data.length; i++) {
    var monthVal = data[i][2];
    if (monthVal instanceof Date &&
        monthVal.getMonth() === now.getMonth() &&
        monthVal.getFullYear() === now.getFullYear()) {
      var row = i + 1;
      sheet.getRange(row, 2).setValue("Yes");
      sheet.getRange(row, 4).setValue(parseFloat(p.chitAmount) || "");
      sheet.getRange(row, 5).setValue(parseFloat(p.discountAmount) || "");
      sheet.getRange(row, 6).setValue(p.name);
      sheet.getRange(row, 7).setValue(p.amountNeedToPay);
      break;
    }
  }

  // Update chitMembers - set Withdraw to "yes" for the winner
  var membersSheet = ss.getSheetByName("chitMembers");
  var mData = membersSheet.getDataRange().getValues();
  var mHeaders = mData[0];
  var nameIdx = mHeaders.indexOf("Name");
  var withdrawIdx = mHeaders.indexOf("Withdraw");
  for (var j = 1; j < mData.length; j++) {
    if (String(mData[j][nameIdx]).trim() === p.name.trim()) {
      membersSheet.getRange(j + 1, withdrawIdx + 1).setValue("Yes");
      break;
    }
  }

  return { success: true };
}

function handleGetReminderData(fileName) {
  var ss = getSpreadsheetByName(fileName);
  var sheet = ss.getSheetByName("chitNumberDetails");
  var data = sheet.getDataRange().getValues();
  var now = new Date();
  var amountPerPerson = "0";

  for (var i = 1; i < data.length; i++) {
    var monthVal = data[i][2];
    if (monthVal instanceof Date &&
        monthVal.getMonth() === now.getMonth() &&
        monthVal.getFullYear() === now.getFullYear()) {
      amountPerPerson = String(data[i][6] || "0");
      break;
    }
  }

  var gpay = "";
  var detailsSheet = ss.getSheetByName("chitDetails");
  if (detailsSheet) {
    var dData = detailsSheet.getDataRange().getValues();
    var dHeaders = dData[0];
    var gpayIdx = dHeaders.indexOf("Gpay");
    if (gpayIdx >= 0 && dData.length > 1) {
      gpay = String(dData[1][gpayIdx] || "");
    }
  }

  return { amountPerPerson: amountPerPerson, gpay: gpay };
}

function handleGetContactNumber(fileName) {
  var ss = getSpreadsheetByName(fileName);
  var detailsSheet = ss.getSheetByName("chitDetails");
  if (!detailsSheet) return { contactNumber: "" };
  var dData = detailsSheet.getDataRange().getValues();
  var dHeaders = dData[0];
  var cnIdx = dHeaders.indexOf("Contact Number");
  if (cnIdx >= 0 && dData.length > 1) {
    return { contactNumber: String(dData[1][cnIdx] || "") };
  }
  return { contactNumber: "" };
}

// ==================== BATCH ENDPOINT ====================
// Returns all data for a chit file in ONE call (members, chitNumber, reminderData, contactNumber)

function handleGetAllChitData(fileName) {
  var ss = getSpreadsheetByName(fileName);
  var now = new Date();

  // --- chitMembers ---
  var members = [];
  var activeMembers = [];
  var membersSheet = ss.getSheetByName("chitMembers");
  if (membersSheet) {
    var mData = membersSheet.getDataRange().getValues();
    var mHeaders = mData[0];
    var nameIdx = mHeaders.indexOf("Name");
    var mobileIdx = mHeaders.indexOf("MobileNumber");
    var withdrawIdx = mHeaders.indexOf("Withdraw");
    for (var i = 1; i < mData.length; i++) {
      var name = mData[i][nameIdx];
      var mobile = mData[i][mobileIdx];
      if (name && String(name).trim() && mobile) {
        var m = { name: String(name).trim(), mobile: String(mobile).trim() };
        members.push(m);
        var withdraw = withdrawIdx >= 0 ? String(mData[i][withdrawIdx]).trim().toLowerCase() : "no";
        if (withdraw !== "Yes") activeMembers.push(m);
      }
    }
  }

  // --- chitNumberDetails ---
  var chitNumber = "";
  var noCount = 0;
  var amountPerPerson = 0;
  var conductedStatus = "";
  var numSheet = ss.getSheetByName("chitNumberDetails");
  if (numSheet) {
    var nData = numSheet.getDataRange().getValues();
    for (var j = 1; j < nData.length; j++) {
      var conducted = String(nData[j][1]).trim().toLowerCase();
      if (conducted === "no") noCount++;
      var monthVal = nData[j][2];
      if (monthVal instanceof Date && monthVal.getMonth() === now.getMonth() && monthVal.getFullYear() === now.getFullYear()) {
        chitNumber = nData[j][0];
        amountPerPerson = nData[j][6] || 0;
        conductedStatus = conducted;
      }
    }
  }

  // --- chitDetails ---
  var totalAmount = 0, chitName = "", gpay = "", contactNumber = "", balanceChit = "";
  var detailsSheet = ss.getSheetByName("chitDetails");
  if (detailsSheet) {
    var dData = detailsSheet.getDataRange().getValues();
    var dHeaders = dData[0];
    if (dData.length > 1) {
      var row = dData[1];
      var idx;
      idx = dHeaders.indexOf("Chit Amount"); if (idx >= 0) totalAmount = row[idx] || 0;
      idx = dHeaders.indexOf("Chit Name"); if (idx >= 0) chitName = String(row[idx] || "");
      idx = dHeaders.indexOf("Gpay"); if (idx >= 0) gpay = String(row[idx] || "");
      idx = dHeaders.indexOf("Contact Number"); if (idx >= 0) contactNumber = String(row[idx] || "");
      idx = dHeaders.indexOf("Balance Chit"); if (idx >= 0) balanceChit = row[idx];
    }
  }

  return {
    members: members,
    activeMembers: activeMembers,
    chitNumber: chitNumber,
    chitRemaining: noCount - 1,
    amountPerPerson: amountPerPerson,
    totalAmount: totalAmount,
    chitName: chitName,
    gpay: gpay,
    contactNumber: contactNumber,
    conducted: conductedStatus,
    balanceChit: balanceChit
  };
}

// ==================== CHIT VIEW DATA ====================
// Returns full sheet data for the view page

function handleGetChitViewData(fileName) {
  var ss = getSpreadsheetByName(fileName);

  // --- chitDetails (single row of key-value pairs) ---
  var chitDetails = {};
  var detailsSheet = ss.getSheetByName("chitDetails");
  if (detailsSheet) {
    var dData = detailsSheet.getDataRange().getValues();
    var dHeaders = dData[0];
    if (dData.length > 1) {
      for (var i = 0; i < dHeaders.length; i++) {
        var key = String(dHeaders[i]).trim();
        if (key) {
          var val = dData[1][i];
          chitDetails[key] = (val instanceof Date) ? Utilities.formatDate(val, Session.getScriptTimeZone(), "dd-MM-yyyy") : (val !== null && val !== undefined ? String(val) : "");
        }
      }
    }
  }

  // --- chitNumberDetails (all rows with headers) ---
  var chitNumberRows = [];
  var chitNumberHeaders = [];
  var numSheet = ss.getSheetByName("chitNumberDetails");
  if (numSheet) {
    var nData = numSheet.getDataRange().getValues();
    var nHeaders = nData[0];
    for (var h = 0; h < nHeaders.length; h++) {
      var nh = String(nHeaders[h]).trim();
      if (nh) chitNumberHeaders.push(nh);
    }
    for (var j = 1; j < nData.length; j++) {
      // Skip empty rows
      var firstVal = nData[j][0];
      if (firstVal === "" || firstVal === null || firstVal === undefined) continue;
      var row = {};
      for (var k = 0; k < nHeaders.length; k++) {
        var hdr = String(nHeaders[k]).trim();
        if (hdr) {
          var v = nData[j][k];
          row[hdr] = (v instanceof Date) ? Utilities.formatDate(v, Session.getScriptTimeZone(), "dd-MM-yyyy") : (v !== null && v !== undefined ? v : "");
        }
      }
      chitNumberRows.push(row);
    }
  }

  // --- chitMembers (all rows with headers) ---
  var chitMembers = [];
  var chitMemberHeaders = [];
  var membersSheet = ss.getSheetByName("chitMembers");
  if (membersSheet) {
    var mData = membersSheet.getDataRange().getValues();
    var mHeaders = mData[0];
    for (var mh = 0; mh < mHeaders.length; mh++) {
      var rawH = mHeaders[mh];
      var mhStr = (rawH instanceof Date) ? Utilities.formatDate(rawH, Session.getScriptTimeZone(), "MMM-yyyy") : String(rawH).trim();
      if (mhStr) chitMemberHeaders.push(mhStr);
    }
    for (var m = 1; m < mData.length; m++) {
      var mRow = {};
      for (var n = 0; n < mHeaders.length; n++) {
        var rawHdr = mHeaders[n];
        var mHdr = (rawHdr instanceof Date) ? Utilities.formatDate(rawHdr, Session.getScriptTimeZone(), "MMM-yyyy") : String(rawHdr).trim();
        if (mHdr) {
          var mv = mData[m][n];
          mRow[mHdr] = (mv instanceof Date) ? Utilities.formatDate(mv, Session.getScriptTimeZone(), "dd-MM-yyyy") : (mv !== null && mv !== undefined ? mv : "");
        }
      }
      var sno = mRow["S.No"] !== undefined ? mRow["S.No"] : mRow["S.NO"] !== undefined ? mRow["S.NO"] : mRow["SNo"];
      if (sno !== "" && sno !== null && sno !== undefined) {
        chitMembers.push(mRow);
      }
    }
  }

  return {
    chitDetails: chitDetails,
    chitNumberRows: chitNumberRows,
    chitNumberHeaders: chitNumberHeaders,
    chitMembers: chitMembers,
    chitMemberHeaders: chitMemberHeaders
  };
}

// ==================== BULK ENDPOINT ====================
// Returns ALL chit files' data in ONE call — eliminates N separate HTTP calls

function handleGetAllFilesData() {
  var folder = getChitDataFolder();
  if (!folder) return { files: {}, folders: [], folderFiles: {} };

  var result = { files: {}, folders: [], folderFiles: {} };

  var subFolders = folder.getFolders();
  while (subFolders.hasNext()) {
    var subFolder = subFolders.next();
    var folderName = subFolder.getName();
    result.folders.push(folderName);
    result.folderFiles[folderName] = [];

    var files = subFolder.getFiles();
    while (files.hasNext()) {
      var file = files.next();
      var mime = file.getMimeType();
      if (mime !== "application/vnd.google-apps.spreadsheet" &&
          mime !== "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") continue;

      var fileName = file.getName();
      result.folderFiles[folderName].push(fileName);

      // Retry up to 2 times with delay to handle Drive quota errors
      var maxRetries = 2;
      for (var attempt = 0; attempt <= maxRetries; attempt++) {
        try {
          if (attempt > 0) Utilities.sleep(2000); // Wait 2s before retry

          var ss = _openSpreadsheet(file, mime, subFolder);
          result.files[fileName] = _extractFileData(ss);
          break; // Success, exit retry loop
        } catch (err) {
          if (attempt < maxRetries && err.message && err.message.indexOf("Drive") >= 0) {
            // Drive quota error — retry after delay
            Utilities.sleep(3000);
          } else {
            result.files[fileName] = { error: err.message };
            break;
          }
        }
      }

      // Small delay between files to avoid hitting Drive API quota
      Utilities.sleep(500);
    }
  }

  result.folders.sort();
  return result;
}

function _openSpreadsheet(file, mime, subFolder) {
  if (mime === "application/vnd.google-apps.spreadsheet") {
    return SpreadsheetApp.open(file);
  } else {
    // Convert xlsx to Google Sheets
    var converted = Drive.Files.copy(
      { title: file.getName(), parents: [{ id: subFolder.getId() }], mimeType: "application/vnd.google-apps.spreadsheet" },
      file.getId()
    );
    file.setTrashed(true);
    return SpreadsheetApp.openById(converted.id);
  }
}

function _extractFileData(ss) {
  var now = new Date();

  // --- chitMembers ---
  var members = [], activeMembers = [];
  var membersSheet = ss.getSheetByName("chitMembers");
  if (membersSheet) {
    var mData = membersSheet.getDataRange().getValues();
    var mHeaders = mData[0];
    var nameIdx = mHeaders.indexOf("Name");
    var mobileIdx = mHeaders.indexOf("MobileNumber");
    var withdrawIdx = mHeaders.indexOf("Withdraw");
    for (var i = 1; i < mData.length; i++) {
      var name = mData[i][nameIdx];
      var mobile = mData[i][mobileIdx];
      if (name && String(name).trim() && mobile) {
        var m = { name: String(name).trim(), mobile: String(mobile).trim() };
        members.push(m);
        var withdraw = withdrawIdx >= 0 ? String(mData[i][withdrawIdx]).trim().toLowerCase() : "no";
        if (withdraw !== "Yes") activeMembers.push(m);
      }
    }
  }

  // --- chitNumberDetails ---
  var chitNumber = "", noCount = 0, amountPerPerson = 0, conductedStatus = "";
  var chitNumberRows = [], chitNumberHeaders = [];
  var numSheet = ss.getSheetByName("chitNumberDetails");
  if (numSheet) {
    var nData = numSheet.getDataRange().getValues();
    var nHeaders = nData[0];
    for (var h = 0; h < nHeaders.length; h++) {
      var nh = String(nHeaders[h]).trim();
      if (nh) chitNumberHeaders.push(nh);
    }
    for (var j = 1; j < nData.length; j++) {
      var conducted = String(nData[j][1]).trim().toLowerCase();
      if (conducted === "no") noCount++;
      var monthVal = nData[j][2];
      if (monthVal instanceof Date && monthVal.getMonth() === now.getMonth() && monthVal.getFullYear() === now.getFullYear()) {
        chitNumber = nData[j][0];
        amountPerPerson = nData[j][6] || 0;
        conductedStatus = conducted;
      }
      // Build view row
      var firstVal = nData[j][0];
      if (firstVal !== "" && firstVal !== null && firstVal !== undefined) {
        var row = {};
        for (var k = 0; k < nHeaders.length; k++) {
          var hdr = String(nHeaders[k]).trim();
          if (hdr) {
            var v = nData[j][k];
            row[hdr] = (v instanceof Date) ? Utilities.formatDate(v, Session.getScriptTimeZone(), "dd-MM-yyyy") : (v !== null && v !== undefined ? v : "");
          }
        }
        chitNumberRows.push(row);
      }
    }
  }

  // --- chitDetails ---
  var totalAmount = 0, chitName = "", gpay = "", contactNumber = "", balanceChit = "";
  var chitDetails = {};
  var detailsSheet = ss.getSheetByName("chitDetails");
  if (detailsSheet) {
    var dData = detailsSheet.getDataRange().getValues();
    var dHeaders = dData[0];
    if (dData.length > 1) {
      var dRow = dData[1];
      var idx;
      idx = dHeaders.indexOf("Chit Amount"); if (idx >= 0) totalAmount = dRow[idx] || 0;
      idx = dHeaders.indexOf("Chit Name"); if (idx >= 0) chitName = String(dRow[idx] || "");
      idx = dHeaders.indexOf("Gpay"); if (idx >= 0) gpay = String(dRow[idx] || "");
      idx = dHeaders.indexOf("Contact Number"); if (idx >= 0) contactNumber = String(dRow[idx] || "");
      idx = dHeaders.indexOf("Balance Chit"); if (idx >= 0) balanceChit = dRow[idx];
      // Build full details map
      for (var di = 0; di < dHeaders.length; di++) {
        var dkey = String(dHeaders[di]).trim();
        if (dkey) {
          var dval = dRow[di];
          chitDetails[dkey] = (dval instanceof Date) ? Utilities.formatDate(dval, Session.getScriptTimeZone(), "dd-MM-yyyy") : (dval !== null && dval !== undefined ? String(dval) : "");
        }
      }
    }
  }

  // --- chitMembers view data (with formatted headers) ---
  var chitMembersView = [], chitMemberHeaders = [];
  if (membersSheet) {
    var mvData = membersSheet.getDataRange().getValues();
    var mvHeaders = mvData[0];
    for (var mh = 0; mh < mvHeaders.length; mh++) {
      var rawH = mvHeaders[mh];
      var mhStr = (rawH instanceof Date) ? Utilities.formatDate(rawH, Session.getScriptTimeZone(), "MMM-yyyy") : String(rawH).trim();
      if (mhStr) chitMemberHeaders.push(mhStr);
    }
    for (var mv = 1; mv < mvData.length; mv++) {
      var mRow = {};
      for (var mn = 0; mn < mvHeaders.length; mn++) {
        var rawHdr = mvHeaders[mn];
        var mHdr = (rawHdr instanceof Date) ? Utilities.formatDate(rawHdr, Session.getScriptTimeZone(), "MMM-yyyy") : String(rawHdr).trim();
        if (mHdr) {
          var mvv = mvData[mv][mn];
          mRow[mHdr] = (mvv instanceof Date) ? Utilities.formatDate(mvv, Session.getScriptTimeZone(), "dd-MM-yyyy") : (mvv !== null && mvv !== undefined ? mvv : "");
        }
      }
      var sno = mRow["S.No"] !== undefined ? mRow["S.No"] : mRow["S.NO"] !== undefined ? mRow["S.NO"] : mRow["SNo"];
      if (sno !== "" && sno !== null && sno !== undefined) {
        chitMembersView.push(mRow);
      }
    }
  }

  return {
    members: members,
    activeMembers: activeMembers,
    chitNumber: chitNumber,
    chitRemaining: noCount - 1,
    amountPerPerson: amountPerPerson,
    totalAmount: totalAmount,
    chitName: chitName,
    gpay: gpay,
    contactNumber: contactNumber,
    conducted: conductedStatus,
    balanceChit: balanceChit,
    chitDetails: chitDetails,
    chitNumberRows: chitNumberRows,
    chitNumberHeaders: chitNumberHeaders,
    chitMembers: chitMembersView,
    chitMemberHeaders: chitMemberHeaders
  };
}

function handleUpdateMemberPayment(fileName, p) {
  var ss = getSpreadsheetByName(fileName);
  var sheet = ss.getSheetByName("chitMembers");
  if (!sheet) return { success: false, error: "chitMembers sheet not found" };

  var data = sheet.getDataRange().getValues();
  var headers = data[0];

  // Find the member name column
  var nameIdx = headers.indexOf("Name");
  if (nameIdx < 0) return { success: false, error: "Name column not found" };

  // Find the month column - headers may be Date objects, so compare formatted
  var colIdx = -1;
  for (var c = 0; c < headers.length; c++) {
    var h = headers[c];
    var headerStr = (h instanceof Date) ? Utilities.formatDate(h, Session.getScriptTimeZone(), "MMM-yyyy") : String(h).trim();
    if (headerStr === p.month) {
      colIdx = c;
      break;
    }
  }
  if (colIdx < 0) return { success: false, error: "Month column not found: " + p.month };

  // Find the member row by name
  for (var r = 1; r < data.length; r++) {
    if (String(data[r][nameIdx]).trim() === String(p.memberName).trim()) {
      var newVal = p.status === "Paid" ? "Paid" : "Not Paid";
      sheet.getRange(r + 1, colIdx + 1).setValue(newVal);
      return { success: true, value: newVal };
    }
  }
  return { success: false, error: "Member not found: " + p.memberName };
}

