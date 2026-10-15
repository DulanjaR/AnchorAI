"""Scenario pools for the synthetic checkpoint -> restart-summary data (Model 2).

Every field is written the way a student might note it, in a form that fits the sentence frames in
generate_data.py:
  goal, next_step, open_items   verb phrases (no leading "to")
  completed, resources          noun phrases
  working_point                 noun phrase that follows "You stopped at ..."
  problem                       a question or a statement (may be first person)
All text here is invented for the data set and marked as synthetic.
"""

FAMILIES = {
    "hotel_site": {
        "split": "train", "kind": "code", "complexity": ["moderate"],
        "titles": ["Hotel booking website", "Hotel reservation web app"],
        "goal": [
            "finish the hotel booking website for the web technologies assignment",
            "build a booking site where guests can search rooms and book them",
            "complete the front end of the hotel reservation system before the demo",
        ],
        "completed": [
            "login.html, register.html and home.html",
            "the room listing page and the search form",
            "the navigation bar and the footer on every page",
            "the css layout for the home page",
        ],
        "working_point": [
            "contact.html, where the form has name and email fields but no submit handler",
            "the booking form, where the date picker is not connected yet",
            "booking.js, in the middle of the price calculation function",
            "the room details page, where the image gallery is half styled",
            "the confirmation page, which still shows placeholder text",
        ],
        "problem": [
            "should the email be validated in javascript or on the server?",
            "the date picker breaks on safari",
            "how do i keep the selected room when the page reloads?",
            "i cannot decide between a modal and a new page for the booking summary",
            "the form submits twice when i press enter",
        ],
        "next_step": [
            "add the submit button and connect the form to the backend",
            "write the price calculation for the selected dates",
            "style the image gallery for small screens",
            "replace the placeholder text on the confirmation page",
            "test the booking form in two browsers",
        ],
        "resources": [
            "figma ui link, contact.html",
            "booking.js and the room images folder",
            "assignment brief pdf, bootstrap docs",
        ],
        "open_items": [
            "validate email format", "show an error message under the field", "add a loading state to the search button",
            "make the navbar collapse on mobile", "save the booking to local storage", "add alt text to the room images",
            "check the form on safari",
        ],
    },
    "bookstore_php": {
        "split": "train", "kind": "code", "complexity": ["complex"],
        "titles": ["Online bookstore (PHP and MySQL)", "Bookstore shopping cart"],
        "goal": [
            "build an online bookstore with a cart and checkout using php and mysql",
            "finish the php backend so customers can order books",
            "get the shopping cart working end to end",
        ],
        "completed": [
            "the database tables for books, customers and orders",
            "the book listing page that reads from mysql",
            "the login and logout pages with sessions",
            "the admin page for adding books",
        ],
        "working_point": [
            "cart.php, where items are added but the quantity cannot be changed",
            "checkout.php, in the middle of the order insert query",
            "the search page, where the sql query returns duplicates",
            "the admin page, where the image upload is not saved yet",
            "config.php, where the database connection fails on my second laptop",
        ],
        "problem": [
            "how do i stop sql injection in the search form?",
            "the cart empties after login",
            "should the cart live in the session or in the database?",
            "i get a duplicate entry error when two orders are placed together",
            "the price shows 3 decimal places",
        ],
        "next_step": [
            "finish the order insert query in checkout.php",
            "add an update quantity button to the cart",
            "fix the duplicate rows in the search query",
            "save the uploaded cover image on the admin page",
            "write three test orders and check the totals",
        ],
        "resources": [
            "er diagram, schema.sql",
            "php manual pages for sessions",
            "xampp project folder",
        ],
        "open_items": [
            "use prepared statements in search.php", "add a quantity field in cart.php", "hash the passwords",
            "limit the admin page to admin users", "format prices with two decimals", "add a delete book button",
            "write the readme",
        ],
    },
    "portfolio": {
        "split": "train", "kind": "code", "complexity": ["simple"],
        "titles": ["Personal portfolio website", "Portfolio site for internship applications"],
        "goal": [
            "publish a clean portfolio website with three projects",
            "finish the portfolio before the internship applications",
            "make the portfolio work well on phones",
        ],
        "completed": [
            "the home page and the about section",
            "the css variables and the colour scheme",
            "the project cards layout",
        ],
        "working_point": [
            "the projects section, where only two of the three cards have text",
            "style.css, in the middle of the media queries",
            "the contact section, where the links are placeholders",
            "the hero image, which is too large and loads slowly",
        ],
        "problem": [
            "which font pairing looks more professional?",
            "the cards overlap on screens under 600px",
            "i am not sure how many projects to show",
            "should i host it on github pages or netlify?",
        ],
        "next_step": [
            "write the description for the third project card",
            "fix the overlap in the media query",
            "compress the hero image",
            "replace the placeholder links with my real profiles",
        ],
        "resources": [
            "figma mockup, style.css",
            "my cv and the project screenshots",
            "github pages guide",
        ],
        "open_items": [
            "add a favicon", "add a meta description", "link the cv pdf", "test on a phone", "compress the images",
        ],
    },
    "db_report": {
        "split": "train", "kind": "document", "complexity": ["moderate"],
        "titles": ["Database assignment report", "Database design report"],
        "goal": [
            "complete the database assignment report with the er diagram and queries",
            "write the report sections for design, queries and conclusion",
            "finish the report before the submission deadline",
        ],
        "completed": [
            "the er diagram and the normalisation to 3nf",
            "the introduction and the scenario description",
            "the table definitions in sql",
        ],
        "working_point": [
            "the sql queries section, where only two of the six queries are written",
            "the indexing discussion, which is still a list of bullet points",
            "the conclusion, which has a title but no text",
            "the references page, where the style is not consistent",
        ],
        "problem": [
            "should the report explain every query or only the complex ones?",
            "i am not sure if the many-to-many table needs its own primary key",
            "how do i write the left join for orders and customers?",
            "the screenshots are too small to read",
            "which referencing style does the lecturer want?",
        ],
        "next_step": [
            "write the remaining four sql queries with short explanations",
            "turn the indexing bullets into a paragraph",
            "write the conclusion",
            "make the references consistent in ieee style",
            "export the report to pdf and check the page count",
        ],
        "resources": [
            "report_notes.md, the lecture slides on normalisation",
            "assignment brief, sample queries file",
            "mysql workbench model file",
        ],
        "open_items": [
            "sql queries for the reports section", "indexing discussion", "conclusion", "references in ieee format",
            "check the page limit", "add figure captions",
        ],
    },
    "py_cleaning": {
        "split": "train", "kind": "code", "complexity": ["simple"],
        "titles": ["Python data-cleaning script", "Survey data cleaning script"],
        "goal": [
            "write a script that cleans the survey csv and saves a tidy file",
            "finish the data cleaning script for the data science lab",
            "make the cleaning script run without errors on the full dataset",
        ],
        "completed": [
            "the function that loads the csv",
            "the code that drops duplicate rows",
            "the column renaming step",
        ],
        "working_point": [
            "clean.py, in the middle of the function that fills missing ages",
            "the date parsing step, where some rows fail",
            "main.py, where the output path is hard coded",
            "the outlier removal, which uses a fixed threshold for now",
        ],
        "problem": [
            "how should missing ages be filled, with the mean or the median?",
            "the script is slow on the full file",
            "i get a unicode error on row 4021",
            "should outliers be removed or just flagged?",
        ],
        "next_step": [
            "finish the function that fills missing ages",
            "handle the rows where the date format is different",
            "move the output path to a command line argument",
            "run the script on the full file and time it",
        ],
        "resources": [
            "survey_raw.csv, clean.py",
            "pandas documentation, lab sheet",
            "my notes on the data columns",
        ],
        "open_items": [
            "handle missing ages", "fix the date format errors", "remove the hard coded path", "write a docstring",
            "add a simple test", "log how many rows were dropped",
        ],
    },
    "java_library": {
        "split": "train", "kind": "code", "complexity": ["complex"],
        "titles": ["Java library management system", "Library system (Java console app)"],
        "goal": [
            "build a console library system that lets members borrow and return books",
            "finish the borrowing and returning features of the library system",
            "get all the classes working together before the viva",
        ],
        "completed": [
            "the Book and Member classes",
            "the file handling that saves books to a text file",
            "the main menu loop",
        ],
        "working_point": [
            "LoanService.java, in the middle of the return method",
            "the fine calculation, where the number of days is wrong",
            "the Member class, which has no validation yet",
            "the search method, which only finds exact titles",
        ],
        "problem": [
            "should the loans be stored in a list or in a file?",
            "i get a null pointer exception when a member has no loans",
            "how do i sort the books by title?",
            "the fine is charged twice when a book is returned late",
            "i am not sure whether to use an interface for the payment part",
        ],
        "next_step": [
            "finish the return method in LoanService.java",
            "fix the number of days in the fine calculation",
            "add validation for the member id",
            "make the search ignore upper and lower case",
            "write the unit tests for the loan service",
        ],
        "resources": [
            "uml class diagram, LoanService.java",
            "the course java notes and the textbook chapter 8",
            "books.txt sample data",
        ],
        "open_items": [
            "check for null loans", "validate the member id", "make the search case-insensitive",
            "write unit tests for LoanService", "update the uml diagram", "handle the file not found error",
        ],
    },
    "network_lab": {
        "split": "train", "kind": "document", "complexity": ["moderate"],
        "titles": ["Network lab report", "Subnetting and VLAN lab report"],
        "goal": [
            "write up the subnetting and routing lab for the networks module",
            "finish the lab report with the packet tracer screenshots",
            "explain the results of the vlan configuration",
        ],
        "completed": [
            "the topology diagram and the ip addressing table",
            "the subnetting calculations for four subnets",
            "the vlan configuration commands",
        ],
        "working_point": [
            "the routing section, where the static routes are listed but not explained",
            "the testing section, where the ping results are pasted without comments",
            "the screenshots, which are not numbered yet",
            "the discussion, which has two paragraphs",
        ],
        "problem": [
            "why does the ping fail between vlan 10 and vlan 20?",
            "should the commands go in the appendix or in the main text?",
            "i am not sure how to explain the default route",
            "the packet tracer file will not open on the lab computer",
        ],
        "next_step": [
            "explain each static route in one or two sentences",
            "add a comment under every ping screenshot",
            "number the screenshots and refer to them in the text",
            "write the last paragraph of the discussion",
        ],
        "resources": [
            "packet tracer file, lab_sheet.pdf",
            "the lecture on inter-vlan routing",
            "ip addressing table in excel",
        ],
        "open_items": [
            "explain the static routes", "comment on the ping results", "number the figures",
            "add the appendix with the commands", "proofread the discussion",
        ],
    },
    "ui_prototype": {
        "split": "train", "kind": "document", "complexity": ["moderate"],
        "titles": ["Mobile app UI design report", "UI prototype report"],
        "goal": [
            "write the design rationale for the mobile app prototype",
            "complete the ui report with the user flow and the wireframes",
            "document the usability test results",
        ],
        "completed": [
            "the user personas and the problem statement",
            "the low fidelity wireframes for five screens",
            "the colour palette and the typography choices",
        ],
        "working_point": [
            "the user flow section, where only the sign-up flow is drawn",
            "the usability test summary, where the tables are empty",
            "the high fidelity screens, where the profile screen is missing",
            "the accessibility section, which is only a heading",
        ],
        "problem": [
            "how many test participants are enough for this report?",
            "should the report include the failed design ideas?",
            "the figma export looks blurry in the document",
            "i do not know how to present the test results",
        ],
        "next_step": [
            "draw the checkout flow next to the sign-up flow",
            "fill the usability tables with the five test results",
            "design the profile screen in figma",
            "write two paragraphs for the accessibility section",
        ],
        "resources": [
            "figma project link, interview notes",
            "usability test recordings, consent forms",
            "the course guidelines on ui reports",
        ],
        "open_items": [
            "draw the checkout flow", "fill the test result tables", "design the profile screen",
            "write the accessibility section", "export the figures at higher resolution", "add a list of figures",
        ],
    },
    "os_scheduler": {
        "split": "val", "kind": "code", "complexity": ["complex"],
        "titles": ["Operating systems scheduling simulator"],
        "goal": [
            "finish the cpu scheduling simulator for the operating systems assignment",
            "make the simulator show the average waiting time for each algorithm",
            "get round robin and priority scheduling working",
        ],
        "completed": [
            "the first come first served scheduler",
            "the process class and the input parser",
            "the gantt chart printing",
        ],
        "working_point": [
            "scheduler.py, in the middle of the round robin loop",
            "the priority scheduler, where ties are not handled",
            "the waiting time calculation, which is off by one",
            "the input file reader, which fails on empty lines",
        ],
        "problem": [
            "how should ties in priority be broken?",
            "round robin gives a different result from my hand calculation",
            "should the time quantum be a command line option?",
            "i do not understand why the last process never finishes",
        ],
        "next_step": [
            "fix the round robin loop so the last process finishes",
            "decide how ties are broken and implement it",
            "correct the off by one in the waiting time",
            "skip empty lines in the input reader",
        ],
        "resources": [
            "scheduler.py, tests folder",
            "lecture slides on scheduling",
            "hand calculation sheet",
        ],
        "open_items": [
            "fix the last process in round robin", "handle priority ties", "fix the off by one in waiting time",
            "skip empty input lines", "add the time quantum option", "write test cases",
        ],
    },
    "srs_document": {
        "split": "test", "kind": "document", "complexity": ["complex"],
        "titles": ["Software requirements specification", "Clinic booking system SRS"],
        "goal": [
            "complete the software requirements specification for the clinic booking system",
            "write all the functional requirements and the use cases",
            "finish the srs so the team can start the design",
        ],
        "completed": [
            "the introduction and the scope",
            "the list of stakeholders",
            "the first four use cases",
        ],
        "working_point": [
            "the functional requirements, where the numbering stops at FR12",
            "the non-functional requirements, which are only a list of keywords",
            "the use case diagram, where the admin actor is missing",
            "the glossary, which is empty",
        ],
        "problem": [
            "should performance requirements be measurable numbers?",
            "are the reminder emails a functional or a non-functional requirement?",
            "i do not know how detailed the use cases should be",
            "the team disagrees about the priority of the payment feature",
        ],
        "next_step": [
            "continue the functional requirements from FR13",
            "turn each non-functional keyword into one measurable sentence",
            "add the admin actor to the diagram",
            "write the glossary with ten terms",
        ],
        "resources": [
            "srs template, interview notes with the clinic",
            "ieee 830 guide",
            "use case diagram file",
        ],
        "open_items": [
            "functional requirements after FR12", "measurable non-functional requirements",
            "admin actor in the diagram", "glossary", "requirement priorities", "traceability table",
        ],
    },
    "ml_notebook": {
        "split": "test", "kind": "code", "complexity": ["complex"],
        "titles": ["Machine learning mini project", "House price prediction notebook"],
        "goal": [
            "finish the notebook that predicts house prices and explains the results",
            "train and compare two models for the machine learning mini project",
            "write the evaluation section of the notebook",
        ],
        "completed": [
            "the data loading and the first plots",
            "the train and test split",
            "the linear regression baseline",
        ],
        "working_point": [
            "the random forest cell, where the training takes too long",
            "the feature engineering section, where the new columns are not used yet",
            "the evaluation section, which only has the r squared score",
            "the final markdown cell, which has no conclusion",
        ],
        "problem": [
            "why is the random forest worse than the linear model?",
            "should i scale the features before the forest?",
            "the test score is much lower than the training score",
            "i am not sure which metric to report",
        ],
        "next_step": [
            "reduce the number of trees and rerun the forest",
            "use the new columns in the model",
            "add mean absolute error next to r squared",
            "write the conclusion in the last cell",
        ],
        "resources": [
            "housing.csv, project.ipynb",
            "scikit-learn documentation on random forests",
            "lecture notebook on evaluation",
        ],
        "open_items": [
            "use the engineered features", "add mean absolute error", "plot the residuals", "write the conclusion",
            "set random seeds", "clean up unused cells",
        ],
    },
    "security_lab": {
        "split": "test", "kind": "document", "complexity": ["moderate"],
        "titles": ["Cybersecurity lab write-up", "Web security lab report"],
        "goal": [
            "write up the web security lab with the findings and the fixes",
            "finish the lab report on sql injection and password hashing",
            "explain each vulnerability and how it was fixed",
        ],
        "completed": [
            "the lab setup description",
            "the sql injection steps with screenshots",
            "the list of tools that were used",
        ],
        "working_point": [
            "the password hashing section, where only the plain text version is described",
            "the xss section, which has the payload but no explanation",
            "the findings table, where severity is empty",
            "the conclusion, which repeats the introduction",
        ],
        "problem": [
            "should the report show the real payloads or only describe them?",
            "how should the severity of each finding be rated?",
            "i cannot reproduce the xss result at home",
            "the screenshots show my username",
        ],
        "next_step": [
            "describe the hashed version of the login and compare it",
            "write two sentences explaining the xss payload",
            "fill the severity column using the course scale",
            "blur the username in the screenshots",
        ],
        "resources": [
            "lab_sheet.pdf, screenshots folder",
            "owasp top ten page",
            "my terminal notes",
        ],
        "open_items": [
            "hashing section", "explain the xss payload", "severity ratings", "blur personal data in screenshots",
            "rewrite the conclusion", "add references",
        ],
    },
}
