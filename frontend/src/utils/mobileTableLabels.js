// Phone-only progressive enhancement for the administrator tables.
//
// On a phone the admin tables are shown as one card per row (see
// styles/mobile-app.css). A card needs each value labelled with its column, so this
// copies every <th> text onto the matching <td> as `data-label`. It changes no
// data and no behaviour, only adds an attribute, and does nothing on desktop widths.
const PHONE = '(max-width: 767px)'

function labelTables(root = document) {
  root.querySelectorAll('table').forEach((table) => {
    const heads = [...table.querySelectorAll('thead th')].map((th) => th.textContent.trim())
    if (!heads.length) return
    table.querySelectorAll('tbody tr').forEach((row) => {
      const cells = [...row.children].filter((c) => c.tagName === 'TD')
      if (cells.length === 1 && cells[0].colSpan > 1) return // "No records" row
      cells.forEach((cell, i) => {
        const label = heads[i] || (cell.classList.contains('actions') ? 'Actions' : '')
        if (label && cell.dataset.label !== label) cell.dataset.label = label
      })
    })
  })
}

export function startMobileTableLabels() {
  if (typeof window === 'undefined' || !window.matchMedia) return
  const query = window.matchMedia(PHONE)
  let observer = null
  const run = () => labelTables()
  const sync = () => {
    if (query.matches && !observer) {
      run()
      observer = new MutationObserver(run)
      observer.observe(document.body, { childList: true, subtree: true })
    } else if (!query.matches && observer) {
      observer.disconnect()
      observer = null
    }
  }
  query.addEventListener?.('change', sync)
  sync()
}
