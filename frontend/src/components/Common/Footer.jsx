function Footer() {
  return (
    <footer
      id="footer"
      className="mt-auto w-full border-t border-outline-variant bg-surface py-base dark:border-on-surface-variant dark:bg-on-primary-container"
    >
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-gutter px-container-padding md:flex-row">
        <div className="flex items-center gap-2">
          <span className="font-headline-lg text-headline-lg cursor-pointer font-bold text-primary transition-opacity duration-200 hover:opacity-80 dark:text-secondary-fixed">
            Tap&Go
          </span>
        </div>

        <nav className="flex flex-wrap justify-center gap-x-8 gap-y-4" aria-label="Footer navigation">
          <a
            className="font-body-md text-body-md cursor-pointer text-on-surface-variant transition-colors duration-200 hover:text-secondary dark:text-surface-variant dark:hover:text-secondary-fixed"
            href="#"
          >
            Terms of Service
          </a>
          <a
            className="font-body-md text-body-md cursor-pointer text-on-surface-variant transition-colors duration-200 hover:text-secondary dark:text-surface-variant dark:hover:text-secondary-fixed"
            href="#"
          >
            Privacy Policy
          </a>
          <a
            className="font-body-md text-body-md cursor-pointer text-on-surface-variant transition-colors duration-200 hover:text-secondary dark:text-surface-variant dark:hover:text-secondary-fixed"
            href="#"
          >
            Contact Support
          </a>
          <a
            className="font-body-md text-body-md cursor-pointer text-on-surface-variant transition-colors duration-200 hover:text-secondary dark:text-surface-variant dark:hover:text-secondary-fixed"
            href="#"
          >
            Operator Login
          </a>
        </nav>

        <div className="text-center font-body-md text-body-md text-on-surface-variant dark:text-surface-container-low md:text-right">
          © 2026 Tap&Go Mobility. All rights reserved.
        </div>
      </div>
    </footer>
  )
}

export default Footer
