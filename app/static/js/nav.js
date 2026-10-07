/** The site navigation's phone menu: a disclosure button that shows and hides
 *  the links below the 48rem breakpoint (the stylesheet does the layout; this
 *  only tracks open/closed).
 *
 *  `aria-expanded` on the button is the source of truth for assistive tech;
 *  the header's modifier class mirrors it for the CSS.
 */

// Must match the stylesheet's breakpoint where the links go inline. Kept in a
// module-level binding so the MediaQueryList, and the listener on it, live
// as long as the page does.
const wideScreen = window.matchMedia("(min-width: 48rem)");

export function initNav() {
  const header = document.querySelector(".site-header");
  const toggle = header?.querySelector("[data-nav-toggle]");
  if (!toggle) return; // signed-out pages have no nav

  const isOpen = () => toggle.getAttribute("aria-expanded") === "true";

  function setOpen(open) {
    toggle.setAttribute("aria-expanded", String(open));
    header.classList.toggle("site-header--nav-open", open);
  }

  toggle.addEventListener("click", () => setOpen(!isOpen()));

  // Esc closes the menu and puts focus back on the button, so a keyboard
  // user isn't left focused inside a list that just disappeared.
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isOpen()) {
      setOpen(false);
      toggle.focus();
    }
  });

  // A tap anywhere outside the header dismisses the open menu.
  document.addEventListener("click", (event) => {
    if (isOpen() && !header.contains(event.target)) setOpen(false);
  });

  // Past the breakpoint the links are inline and the button is hidden; reset
  // to closed so the menu isn't still open when the window narrows again.
  wideScreen.addEventListener("change", (event) => {
    if (event.matches) setOpen(false);
  });
}
