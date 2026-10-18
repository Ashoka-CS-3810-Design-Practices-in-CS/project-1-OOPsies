function importTimetable(){
    const ttData = []
    const tt = document.querySelector('.table-scrollable table');

    if (!tt) {
        return null
    }
    // get table body
    const rows = tt.querySelectorAll('tbody tr')


    rows.forEach(row => {
        const intervalStr = row.querySelector('td:first-child').innerText.trim() 
        // first element is always time interval
        const ttCells = row.querySelectorAll('td:not(:first-child)')
        // remaining elements are timetable cells

        ttRow = []
        ttCells.forEach(cell => {
            const courseDiv = cell.querySelector('div.LsCol, div.DsCol') 
            // div class for LS and DS
            if (courseDiv) {
                ttRow.push({
                    title: courseDiv.getAttribute('coursename'),
                    course_code: courseDiv.getAttribute('dscode') || courseDiv.getAttribute('lscode'),
                    venue: courseDiv.getAttribute('roomno')
                })
            }
            else {
                ttRow.push({})
            }
        })

        ttData.push({
            interval:intervalStr,
            row:ttRow
        })
    })

    return ttData
}

// Select the node that will be observed for mutations
const targetNode = document.body
// Options for the observer (which mutations to observe)
const config = { attributes: true, childList: true, subtree: true }
// Callback function to execute when mutations are observed
const callback = async (mutationList, observer) => {
    const ttData = importTimetable()
    if (ttData === null) return 
    await browser.storage.local.set({ AshokaTimetable: ttData })
    observer.disconnect()
}

// Create an observer instance linked to the callback function
const observer = new MutationObserver(callback)

// Start observing the target node for configured mutations
observer.observe(targetNode, config)