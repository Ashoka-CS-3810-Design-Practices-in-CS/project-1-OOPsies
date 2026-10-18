document.getElementById('nicegui-frame').src = `https://example.com/`

const btn = document.getElementById('import-btn')

async function sync() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  btn.disabled = !tab?.url?.startsWith('https://ams.ashoka.edu.in/Contents/TimeTable/TimeTableView_Student.aspx')
}

btn.addEventListener('click', async () => {
  chrome.runtime.sendMessage({
    type: 'import-events',
    payload: await browser.storage.local.get(["AshokaTimetable"])
  })
})

sync()

chrome.tabs.onActivated.addListener(sync)
chrome.tabs.onUpdated.addListener(sync)

