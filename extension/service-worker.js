browser.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error(error))

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'import-events') {
    console.log('hello')
    fetch('http://127.0.0.1:5000/api/import', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(message.payload)
      }).then(response => response.json())
        .then(data => {sendResponse({ success: true, data: data })
      }).catch(error => {
        console.log(message.payload)
        console.error('Error:', error)
        sendResponse({ success: false, error: error.message })
      })
    }
  }
)