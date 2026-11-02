document.getElementById('nicegui-frame').src = `https://doable.rupsha.page/`

const btn = document.getElementById('import-btn')
let prevDisabled = null 

async function sync() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  const ttData = await browser.storage.local.get(["AshokaTimetable"])

  btn.disabled = 
  !tab?.url?.startsWith
  ('https://ams.ashoka.edu.in/Contents/TimeTable/TimeTableView_Student.aspx') 
  || !ttData.AshokaTimetable?.length

  if (prevDisabled === true && !btn.disabled) {   // ← new
    location.reload()
    return
  }
  prevDisabled = btn.disabled 
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

