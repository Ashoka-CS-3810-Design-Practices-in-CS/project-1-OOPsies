document.getElementById('nicegui-frame').src = `https://example.com/`

const btn = document.getElementById('analyze-btn')

async function sync() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  btn.disabled = !tab?.url?.startsWith('https://ams.ashoka.edu.in/Contents/TimeTable/TimeTableView_Student.aspx')
}

chrome.tabs.onActivated.addListener(sync)
chrome.tabs.onUpdated.addListener(sync)

sync()