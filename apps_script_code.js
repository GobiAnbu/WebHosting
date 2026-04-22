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
      case "getChitFiles":
        result = handleGetChitFiles();
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
        email: String(data[i][3] || "")
      });
    }
  }
  return users;
}

function handleAddUser(p) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Users");
  if (!sheet) {
    sheet = SpreadsheetApp.getActiveSpreadsheet().insertSheet("Users");
    sheet.appendRow(["username", "password", "role", "email"]);
  }
  sheet.appendRow([p.username, p.password, p.role || "user", p.email || ""]);
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

  // Try exact name match first
  var files = folder.getFilesByName(fileName);
  while (files.hasNext()) {
    var file = files.next();
    var mime = file.getMimeType();
    if (mime === "application/vnd.google-apps.spreadsheet") {
      return SpreadsheetApp.open(file);
    }
    // If it's an xlsx file, convert it to Google Sheets
    if (mime === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") {
      var converted = Drive.Files.copy(
        { title: file.getName(), parents: [{ id: folder.getId() }], mimeType: "application/vnd.google-apps.spreadsheet" },
        file.getId()
      );
      file.setTrashed(true); // Remove the original xlsx
      return SpreadsheetApp.openById(converted.id);
    }
  }

  // Try without extension
  var nameNoExt = fileName.replace(/\.xlsx$/i, "");
  files = folder.getFiles();
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

  throw new Error("File '" + fileName + "' not found in chitData folder. Make sure it is a Google Sheet (not .xlsx). Right-click the file in Drive > Open with > Google Sheets > File > Save as Google Sheets.");
}

function handleGetChitFiles() {
  var folder = getChitDataFolder();
  if (!folder) return [];
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
    if (withdraw !== "yes" && name && String(name).trim()) {
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

  for (var i = 1; i < data.length; i++) {
    var conducted = String(data[i][1]).trim().toLowerCase();
    if (conducted === "no") noCount++;
    var monthVal = data[i][2];
    if (monthVal instanceof Date) {
      if (monthVal.getMonth() === now.getMonth() && monthVal.getFullYear() === now.getFullYear()) {
        chitNumber = data[i][0];
        amountPerPerson = data[i][6] || 0;
      }
    }
  }

  var totalAmount = 0, chitName = "", gpay = "", contactNumber = "";
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
    }
  }

  return {
    chitNumber: chitNumber,
    chitRemaining: noCount - 1,
    amountPerPerson: amountPerPerson,
    totalAmount: totalAmount,
    chitName: chitName,
    gpay: gpay,
    contactNumber: contactNumber
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
      membersSheet.getRange(j + 1, withdrawIdx + 1).setValue("yes");
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
        if (withdraw !== "yes") activeMembers.push(m);
      }
    }
  }

  // --- chitNumberDetails ---
  var chitNumber = "";
  var noCount = 0;
  var amountPerPerson = 0;
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
      }
    }
  }

  // --- chitDetails ---
  var totalAmount = 0, chitName = "", gpay = "", contactNumber = "";
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
    contactNumber: contactNumber
  };
}

