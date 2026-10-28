"""
The three web streams: Frontend, Backend, and Full Stack.

Task briefs are written from the kind of work KLS engineers actually do, which
is the whole claim the platform makes. A task that could be completed by
following a tutorial step for step is not a task — it is a tutorial.
"""

from app.services.chapter_pdf import (
    Chapter,
    bullets,
    code,
    h2,
    h3,
    key,
    note,
    p,
    steps,
    warn,
)
from scripts.curriculum import Stream, TaskSpec

# ===========================================================================
# Frontend Development
# ===========================================================================

FRONTEND = Stream(
    slug="frontend-development",
    title="Frontend Development",
    description=(
        "Build interfaces people can actually use. You will work in React and "
        "TypeScript, handle real application state, make the result accessible "
        "and fast, and deploy it where anyone can open it. Every submission is "
        "read by a KLS engineer who has shipped frontends to production."
    ),
    duration="4 weeks",
    difficulty="beginner",
    icon="layout",
    display_order=1,
    skills=["HTML", "CSS", "JavaScript", "TypeScript", "React", "Accessibility", "Vite"],
    outcomes=[
        "Build a multi-screen React application from a written brief",
        "Manage state without reaching for a library on day one",
        "Make an interface usable with a keyboard and a screen reader",
        "Deploy a production build and explain what the bundler did",
    ],
    tasks=[
        TaskSpec(
            order_number=1,
            title="A responsive product page, from a brief",
            description=(
                "Build a single product page that works from 320px to a desktop "
                "monitor. You are given the content and the constraints, not a "
                "design file — part of the job is making defensible layout "
                "decisions and being able to explain them.\n\n"
                "The page needs: a gallery with a selected image, a title, a "
                "price, a variant picker that changes the price, a quantity "
                "control, and an add-to-cart button that shows what happened. "
                "No backend. State lives in the component."
            ),
            requirements=[
                "React with TypeScript, built with Vite",
                "No CSS framework — write the CSS yourself",
                "Works at 320px with no horizontal scrolling",
                "Every control reachable and operable by keyboard alone",
                "README explains two layout decisions and why you made them",
            ],
            estimated_hours=10,
        ),
        TaskSpec(
            order_number=2,
            title="A searchable, filterable list against a real API",
            description=(
                "Fetch a list from a public API and let the user search, filter "
                "and sort it. The interesting part is not the fetch — it is "
                "everything around it: the loading state, the empty state, the "
                "error state, and what happens when someone types faster than "
                "the network responds.\n\n"
                "Handle all four states explicitly. A spinner that never "
                "resolves is a bug; so is a flash of 'no results' before the "
                "first response arrives."
            ),
            requirements=[
                "Debounced search that does not fire a request per keystroke",
                "Loading, empty, error and success states each visibly handled",
                "Filter state reflected in the URL, so a filtered view is shareable",
                "Requests cancelled or ignored when superseded — no race conditions",
                "Explanation covers how you prevented the out-of-order response bug",
            ],
            estimated_hours=12,
        ),
        TaskSpec(
            order_number=3,
            title="Ship it, and prove it is fast",
            description=(
                "Take task 2 to production. Build it, deploy it to any static "
                "host, then measure it and improve what you measure.\n\n"
                "We are looking for evidence that you understand what your "
                "build tool produced, not for a perfect score. A Lighthouse run "
                "with an honest explanation of the one thing you could not fix "
                "is worth more than a 100 you cannot account for."
            ),
            requirements=[
                "Deployed and publicly reachable over HTTPS",
                "Lighthouse report before and after your improvements, both attached",
                "Bundle size stated, with the largest dependency named",
                "At least one measurable improvement, explained",
                "Accessibility score of 90 or above, with remaining issues listed",
            ],
            estimated_hours=8,
            require_live_demo=True,
        ),
    ],
    chapters=[
        Chapter(
            domain="Frontend Development",
            number=1,
            title="The Browser Is the Platform",
            level="Beginner",
            summary=(
                "Frameworks come and go. The document model, the box model and "
                "the event loop have been constant for twenty years, and almost "
                "every confusing React bug is one of those three showing "
                "through. Start here and the frameworks make sense later."
            ),
            minutes=35,
            outcomes=[
                "Describe what the browser does between receiving HTML and painting",
                "Use flexbox and grid deliberately rather than by trial and error",
                "Explain why a long loop freezes the whole page",
            ],
            blocks=[
                h2("What happens before anything appears"),
                p(
                    "The browser receives a stream of HTML text. It parses it into a "
                    "tree of nodes called the DOM. It fetches and parses the CSS into a "
                    "second structure, works out which rules apply to which node, then "
                    "calculates where everything goes and paints it. Nothing about this "
                    "is magic and all of it is observable."
                ),
                p(
                    "The order matters more than people expect. A stylesheet in the "
                    "head blocks painting, because the browser will not show you text "
                    "it is about to restyle. A script in the head blocks parsing, "
                    "because that script might write more HTML. This is why "
                    "'put the script at the end' was advice for a decade, and why "
                    "`defer` exists now."
                ),
                code(
                    "<!-- blocks parsing: the browser stops and runs this -->\n"
                    "<script src=\"app.js\"></script>\n\n"
                    "<!-- downloads in parallel, runs after parsing finishes -->\n"
                    "<script src=\"app.js\" defer></script>",
                    "two attributes, very different behaviour",
                ),
                note(
                    "Open any site, press F12, and watch the Network panel while you "
                    "reload. The waterfall you are looking at is this paragraph."
                ),
                h2("The box model, which is where the time goes"),
                p(
                    "Every element is a box with content, padding, a border and a "
                    "margin. The confusion that costs beginners hours is what `width` "
                    "refers to. By default it means the content only, so a box with "
                    "`width: 300px` and `padding: 20px` occupies 340 pixels."
                ),
                code(
                    "/* Put this at the top of every stylesheet you write. */\n"
                    "*, *::before, *::after {\n"
                    "  box-sizing: border-box;\n"
                    "}\n\n"
                    "/* Now width means the whole box, which is what you meant. */",
                    "the one line that fixes it",
                ),
                h3("Margins collapse, and that is deliberate"),
                p(
                    "Two vertical margins that touch become one, taking the larger of "
                    "the two. A 20px margin below one paragraph and a 30px margin above "
                    "the next produces a 30px gap, not 50. This looks like a bug and is "
                    "a feature: it stops stacked text accumulating enormous gaps. "
                    "Flexbox and grid do not collapse margins, which is one more reason "
                    "to use them for layout."
                ),
                h2("Flexbox and grid, chosen on purpose"),
                p(
                    "Flexbox lays things out along one axis. Grid lays them out on two. "
                    "That sentence is the entire decision procedure, and almost nobody "
                    "is taught it that way."
                ),
                bullets(
                    "A row of buttons, a navigation bar, a card's internal stack — one "
                    "direction, so flexbox.",
                    "A page skeleton, a photo gallery, anything where columns must line "
                    "up with rows — two directions, so grid.",
                    "Nesting both is normal. A grid of cards where each card is a flex "
                    "column is the most common layout on the web.",
                ),
                code(
                    "/* A card grid that needs no media queries at all. */\n"
                    ".cards {\n"
                    "  display: grid;\n"
                    "  gap: 1rem;\n"
                    "  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));\n"
                    "}",
                    "responsive without a breakpoint",
                ),
                p(
                    "`auto-fit` with `minmax` tells the browser the rule rather than the "
                    "answer: every column at least 16rem, share the leftover space, fit "
                    "as many as will go. At 320px that is one column. On a monitor it is "
                    "five. You wrote no breakpoints and it works at every width in "
                    "between, including the ones you did not test."
                ),
                key("Describe the constraint, not the breakpoint. The browser is better at arithmetic than you are."),
                h2("One thread, and what that costs you"),
                p(
                    "Your JavaScript, the layout engine and the paint all share one "
                    "thread. While your code is running, nothing is painting — the page "
                    "is frozen. Not slow: frozen. Clicks queue up and the browser may "
                    "offer to kill the tab."
                ),
                code(
                    "// Freezes the tab for roughly a second on a laptop,\n"
                    "// and considerably longer on a mid-range phone.\n"
                    "let total = 0;\n"
                    "for (let i = 0; i < 1e9; i++) total += i;\n",
                    "do not ship this",
                ),
                p(
                    "This is why asynchronous code exists. `fetch` does not block, "
                    "because the network wait happens off-thread and your callback is "
                    "queued for when the main thread is free. Understanding that queue "
                    "is what makes `async`/`await` stop feeling like syntax you copy."
                ),
                warn(
                    "A 200ms delay feels instant. 1 second feels slow. 10 seconds and "
                    "people leave. Measure on a mid-range Android phone, not on your "
                    "laptop — that is what most of India is browsing on."
                ),
                h2("Before the next chapter"),
                steps(
                    "Build a page with a header, a sidebar and a content area using "
                    "grid, in a single HTML file with no framework.",
                    "Make it work at 320px without a media query.",
                    "Add a button that disables itself for two seconds when clicked, "
                    "using only the DOM API.",
                    "Open the Performance panel, record a reload, and find the paint.",
                ),
            ],
        ),
        Chapter(
            domain="Frontend Development",
            number=2,
            title="React Without the Cargo Cult",
            level="Intermediate",
            summary=(
                "React is a small idea surrounded by a large amount of folklore. "
                "This chapter is the small idea: state goes in, markup comes "
                "out, and when state changes the function runs again. Nearly "
                "every React bug is a misunderstanding of that last clause."
            ),
            minutes=40,
            outcomes=[
                "Explain what a re-render is and what it is not",
                "Choose where a piece of state should live",
                "Use effects for the narrow job they are actually for",
                "Recognise the stale closure bug before it happens",
            ],
            blocks=[
                h2("A component is a function of its state"),
                p(
                    "Given the same props and the same state, a component returns the "
                    "same markup. When state changes, React calls the function again "
                    "and compares the result with the previous one. That comparison is "
                    "the only clever part, and you can mostly ignore it."
                ),
                p(
                    "What you cannot ignore: the function body runs again, top to "
                    "bottom, every time. Every `const` is a new const. Every function "
                    "you define is a new function. People who think of a component as "
                    "an object that persists get surprised constantly."
                ),
                code(
                    "function Counter() {\n"
                    "  const [count, setCount] = useState(0);\n"
                    "  // This line runs on every single render.\n"
                    "  const doubled = count * 2;\n"
                    "  return <button onClick={() => setCount(count + 1)}>{doubled}</button>;\n"
                    "}",
                    "nothing here survives between renders except state",
                ),
                h2("Where should this state live?"),
                p(
                    "The rule is short: put state in the closest component that needs "
                    "it, and move it up only when a second component needs the same "
                    "value. Moving it higher than necessary re-renders a larger subtree "
                    "than necessary and makes the component harder to reuse."
                ),
                bullets(
                    "Used by one component — keep it there with `useState`.",
                    "Used by a parent and a child — lift it to the parent and pass it "
                    "down.",
                    "Used by two distant cousins — lift to their nearest common "
                    "ancestor, or use context.",
                    "It belongs to the server and you are caching it — that is not "
                    "state, that is a cache. Use a query library.",
                ),
                note(
                    "The last one is the biggest shift. Data you fetched is not "
                    "application state; it is a copy of someone else's state. Treating "
                    "it as a cache with staleness rules removes an entire category of "
                    "bugs you would otherwise write by hand."
                ),
                h2("Effects do one job"),
                p(
                    "`useEffect` exists to synchronise your component with something "
                    "outside React: a subscription, a timer, the document title, a "
                    "network request. That is the list. It is not a place to compute "
                    "values, and it is not a lifecycle hook."
                ),
                code(
                    "// Wrong: an effect that derives state from state.\n"
                    "const [items, setItems] = useState([]);\n"
                    "const [count, setCount] = useState(0);\n"
                    "useEffect(() => { setCount(items.length); }, [items]);\n\n"
                    "// Right: just calculate it. It is already a render.\n"
                    "const count = items.length;",
                    "the most common unnecessary effect",
                ),
                p(
                    "The wrong version renders twice for every change, can show a stale "
                    "count for one frame, and adds a dependency array to keep correct "
                    "forever. The right version cannot be wrong."
                ),
                h3("The cleanup function is not optional"),
                code(
                    "useEffect(() => {\n"
                    "  const controller = new AbortController();\n"
                    "\n"
                    "  fetch(`/api/search?q=${query}`, { signal: controller.signal })\n"
                    "    .then((r) => r.json())\n"
                    "    .then(setResults)\n"
                    "    .catch((e) => { if (e.name !== 'AbortError') setError(e); });\n"
                    "\n"
                    "  // Runs before the next effect and on unmount.\n"
                    "  return () => controller.abort();\n"
                    "}, [query]);",
                    "the fix for out-of-order responses",
                ),
                p(
                    "Without the abort, a slow request for 'ab' can land after a fast "
                    "request for 'abcd' and overwrite the correct results with stale "
                    "ones. The user sees results for something they typed two seconds "
                    "ago. This is the single most common bug in search interfaces and "
                    "it is four lines to prevent."
                ),
                warn(
                    "Task 2 of this internship is graded partly on whether you handled "
                    "this. If your explanation does not mention it, we will ask."
                ),
                h2("Stale closures, explained once"),
                p(
                    "A function defined during a render captures the variables of that "
                    "render. If it runs later — in a timer, in a subscription — it still "
                    "sees the old values. The code looks correct and behaves as though "
                    "time stopped."
                ),
                code(
                    "// Counts to 1 and stays there, forever.\n"
                    "useEffect(() => {\n"
                    "  const id = setInterval(() => setCount(count + 1), 1000);\n"
                    "  return () => clearInterval(id);\n"
                    "}, []);\n\n"
                    "// Counts properly: the updater sees the current value.\n"
                    "useEffect(() => {\n"
                    "  const id = setInterval(() => setCount((c) => c + 1), 1000);\n"
                    "  return () => clearInterval(id);\n"
                    "}, []);",
                    "one character of difference",
                ),
                key("If a value is used inside a callback that outlives the render, use the updater form or a ref."),
                h2("When to reach for memo"),
                p(
                    "Almost never, at first. `useMemo` and `useCallback` are not free — "
                    "they allocate, they add a dependency array to maintain, and they "
                    "make the code harder to read. Use them when you have measured a "
                    "problem in the Profiler, not because a component feels large."
                ),
                p(
                    "The exception worth knowing early: a value passed into a context "
                    "provider should be memoised, because a new object identity on every "
                    "render re-renders every consumer in the tree."
                ),
            ],
        ),
        Chapter(
            domain="Frontend Development",
            number=3,
            title="Accessible, Fast, and Actually Deployed",
            level="Advanced",
            summary=(
                "The difference between a project and a product is everything "
                "in this chapter: it works for people who do not use a mouse, "
                "it loads on a phone on a bad connection, and it is running at "
                "a URL you can send to someone."
            ),
            minutes=35,
            outcomes=[
                "Make an interface fully operable by keyboard",
                "Read a Lighthouse report and act on the right line",
                "Explain what your bundler shipped and why it is that size",
                "Deploy a static build with correct caching",
            ],
            blocks=[
                h2("Accessibility is mostly using the right element"),
                p(
                    "Before any ARIA attribute, use the element that already means what "
                    "you want. A `button` is focusable, activates on Enter and Space, "
                    "announces itself as a button, and works with voice control. A `div` "
                    "with an onClick has none of that, and the four attributes you would "
                    "add to fake it will still be wrong on some device."
                ),
                code(
                    "<!-- Inaccessible: not focusable, not announced, ignores Enter. -->\n"
                    "<div class=\"btn\" onclick=\"submit()\">Submit</div>\n\n"
                    "<!-- Accessible, shorter, and free. -->\n"
                    "<button type=\"submit\">Submit</button>",
                    "the first rule of ARIA is not to use ARIA",
                ),
                h3("The four things to check on every screen"),
                steps(
                    "Unplug the mouse. Can you reach and operate everything with Tab, "
                    "Enter, Space and the arrow keys?",
                    "Is the focus ring visible? If you removed the outline, you have "
                    "made the site unusable for keyboard users.",
                    "Does every image have alt text, and is it empty for decorative "
                    "images rather than describing the filename?",
                    "Does every input have a real `<label>` associated with it? A "
                    "placeholder is not a label — it disappears when you type.",
                ),
                note(
                    "Roughly one in twelve men has some colour vision deficiency. Never "
                    "use colour as the only signal: a red border needs an error message "
                    "beside it."
                ),
                h2("Reading a Lighthouse report properly"),
                p(
                    "The score is a weighted average and chasing it directly teaches you "
                    "nothing. The metrics are what matter, and only two usually need "
                    "your attention."
                ),
                bullets(
                    "Largest Contentful Paint — when the main thing appears. Usually "
                    "fixed by making the hero image smaller or loading a font better.",
                    "Cumulative Layout Shift — how much the page jumps while loading. "
                    "Usually fixed by setting width and height on images.",
                    "Total Blocking Time — how long the main thread was frozen. Usually "
                    "means too much JavaScript.",
                ),
                code(
                    "<!-- CLS cause: the browser does not know how tall this is until\n"
                    "     it downloads, so everything below jumps when it arrives. -->\n"
                    "<img src=\"/hero.jpg\" alt=\"\">\n\n"
                    "<!-- Fixed: space is reserved before the bytes arrive. -->\n"
                    "<img src=\"/hero.jpg\" alt=\"\" width=\"1200\" height=\"630\">",
                    "the cheapest performance fix there is",
                ),
                h2("Know what you shipped"),
                p(
                    "Run your build and look at the output. If a single dependency is "
                    "40% of your bundle, you should be able to name it and say why it is "
                    "worth that. Frequently it is a date library imported whole for one "
                    "function, or an icon set imported as a barrel file."
                ),
                code(
                    "# Vite prints a size table on every build. Read it.\n"
                    "npm run build\n\n"
                    "# Then look at what is actually inside the big chunk.\n"
                    "npx vite-bundle-visualizer",
                    "two commands, before every deploy",
                ),
                warn(
                    "`import { Icon } from 'some-icon-pack'` can pull the entire pack "
                    "into your bundle if the package is not tree-shakeable. Check the "
                    "size table after adding any dependency, not at the end of the "
                    "project."
                ),
                h2("Deploying a static build"),
                p(
                    "A production build is a folder of files. Any static host will serve "
                    "it. The two things that are easy to get wrong are caching and "
                    "client-side routing."
                ),
                bullets(
                    "Hashed asset filenames can be cached forever. `index.html` must "
                    "never be cached, or returning users get an old page pointing at "
                    "assets that no longer exist.",
                    "If you use client-side routing, every unknown path must serve "
                    "`index.html` rather than 404, or a deep link opened directly will "
                    "fail while the same link clicked inside the app works.",
                ),
                key("The deep-link 404 is the bug that gets found by the person you sent the link to, which is the worst time to find it."),
                h2("What we look for in your submission"),
                p(
                    "An honest report beats a perfect one. A Lighthouse score of 78 with "
                    "a paragraph explaining that the remaining cost is a third-party "
                    "embed you cannot defer tells us you understand the system. A 100 "
                    "with no explanation tells us you ran a tool."
                ),
            ],
        ),
    ],
)


# ===========================================================================
# Backend Development
# ===========================================================================

BACKEND = Stream(
    slug="backend-development",
    title="Backend Development",
    description=(
        "Design and build the service behind the interface. You will model "
        "data properly, write an HTTP API other people can use, authenticate "
        "requests without inventing your own scheme, and make the thing "
        "observable enough to run. Python and PostgreSQL throughout."
    ),
    duration="6 weeks",
    difficulty="intermediate",
    icon="server",
    display_order=2,
    skills=["Python", "FastAPI", "PostgreSQL", "SQL", "REST", "Authentication", "Testing"],
    outcomes=[
        "Model a domain in a relational schema and justify the constraints",
        "Build a documented HTTP API with real validation",
        "Implement authentication and authorisation correctly",
        "Write tests that would catch a regression you actually fear",
    ],
    tasks=[
        TaskSpec(
            order_number=1,
            title="Design the schema before writing any endpoint",
            description=(
                "You are given a domain in prose — a small library lending "
                "system — and must produce a relational schema for it, as "
                "migrations, with a short written defence.\n\n"
                "We are looking for constraints. A schema where any column can "
                "be null and nothing is unique is not a design, it is a "
                "spreadsheet. Every constraint you add is a bug that becomes "
                "impossible rather than merely unlikely."
            ),
            requirements=[
                "Migrations that run forward and reverse cleanly",
                "Foreign keys with an explicit ON DELETE behaviour, each justified",
                "At least two CHECK or UNIQUE constraints with reasoning",
                "An index on every column you filter or join on, and no others",
                "A written note on one thing you deliberately did not normalise",
            ],
            estimated_hours=10,
        ),
        TaskSpec(
            order_number=2,
            title="A CRUD API that survives a hostile client",
            description=(
                "Build the HTTP API over your schema. The requirement that "
                "matters is that it behaves correctly when the caller is wrong: "
                "missing fields, wrong types, values out of range, IDs that do "
                "not exist, and the same request sent twice.\n\n"
                "Every one of those should produce a specific status code and a "
                "message a client developer can act on. A 500 is a bug in your "
                "code, not a bad request."
            ),
            requirements=[
                "Full CRUD with correct status codes — 200, 201, 204, 400, 404, 409, 422",
                "Request and response schemas validated, not hand-checked",
                "Pagination on every list endpoint",
                "OpenAPI documentation that is accurate, not just present",
                "Tests for the failure cases, not only the happy path",
            ],
            estimated_hours=14,
        ),
        TaskSpec(
            order_number=3,
            title="Authentication, authorisation and an audit trail",
            description=(
                "Add accounts to your API. Registration, login, and "
                "role-based access so that an ordinary user cannot reach an "
                "administrator's endpoints or read another user's records.\n\n"
                "Hash passwords with a real password hash. Do not invent a "
                "token format. Then prove the authorisation works by writing "
                "the test that tries to break it."
            ),
            requirements=[
                "Passwords hashed with bcrypt or argon2 — never a plain hash",
                "Tokens with an expiry, and a documented refresh or re-login path",
                "A test proving user A cannot read or modify user B's records",
                "A test proving a non-admin gets 403 on every admin route",
                "Significant actions written to an audit table with actor and timestamp",
            ],
            estimated_hours=14,
        ),
    ],
    chapters=[
        Chapter(
            domain="Backend Development",
            number=1,
            title="Data First: Schemas, Constraints and SQL",
            level="Beginner",
            summary=(
                "The schema outlives the code. Frameworks get rewritten and "
                "endpoints get renamed, but the data and its shape survive, and "
                "a bad schema makes every piece of code touching it worse "
                "forever. This chapter is about getting that part right."
            ),
            minutes=40,
            outcomes=[
                "Model a domain into tables with sensible keys",
                "Choose a deletion behaviour for each relationship deliberately",
                "Write joins and aggregates without guessing",
                "Know which columns deserve an index and which do not",
            ],
            blocks=[
                h2("Tables are nouns, rows are facts"),
                p(
                    "Start by listing the things your domain talks about: a student, a "
                    "book, a loan. Each becomes a table. Each row is one assertion of "
                    "fact. If you find yourself storing two facts in one row — a "
                    "comma-separated list of authors, say — you have found a table you "
                    "have not created yet."
                ),
                code(
                    "-- Storing a list in a column. Looks convenient, is not.\n"
                    "CREATE TABLE books (\n"
                    "  id      bigserial PRIMARY KEY,\n"
                    "  title   text NOT NULL,\n"
                    "  authors text              -- 'Hugo, Ananya, Rafael'\n"
                    ");\n\n"
                    "-- Now answer: how many books has Ananya written?\n"
                    "-- You cannot, without string matching that will find 'Ananyaa'.",
                    "the mistake that is hardest to undo later",
                ),
                p(
                    "The fix is a second table and a join table. It feels like more work "
                    "for an afternoon and saves you a rewrite in a year, because every "
                    "question you will later want to ask becomes a query rather than a "
                    "migration."
                ),
                h2("Constraints are the cheapest tests you will ever write"),
                p(
                    "A constraint is a rule the database enforces on every write, "
                    "forever, including writes from a script someone runs by hand at "
                    "midnight. Application-level validation only protects the path that "
                    "goes through your application."
                ),
                code(
                    "CREATE TABLE loans (\n"
                    "  id          bigserial PRIMARY KEY,\n"
                    "  book_id     bigint NOT NULL REFERENCES books(id) ON DELETE RESTRICT,\n"
                    "  student_id  bigint NOT NULL REFERENCES students(id) ON DELETE CASCADE,\n"
                    "  taken_at    timestamptz NOT NULL DEFAULT now(),\n"
                    "  due_at      timestamptz NOT NULL,\n"
                    "  returned_at timestamptz,\n"
                    "\n"
                    "  CHECK (due_at > taken_at),\n"
                    "  CHECK (returned_at IS NULL OR returned_at >= taken_at)\n"
                    ");",
                    "every line here prevents a specific bug",
                ),
                h3("Choosing ON DELETE, every time"),
                bullets(
                    "`CASCADE` — the child has no meaning without the parent. Delete a "
                    "student, delete their loans.",
                    "`RESTRICT` — deletion should be refused. You must not delete a book "
                    "that is currently on loan.",
                    "`SET NULL` — the link is optional history. The admin who approved "
                    "something leaves; the approval record stays.",
                ),
                warn(
                    "There is no sensible default here. Leaving it unspecified gives you "
                    "`NO ACTION`, which you did not choose and probably did not want."
                ),
                h2("Timestamps, and the bug that hides for six months"),
                p(
                    "Use `timestamptz`, always. A `timestamp` without a timezone is a "
                    "number with no meaning attached — it does not record what it was "
                    "relative to. The symptom appears when your server runs in UTC and "
                    "your users are in IST: everything is five and a half hours out, but "
                    "only sometimes, because some writes went through code that happened "
                    "to be timezone-aware."
                ),
                key("Store instants in UTC with a timezone. Convert to local time at the edge, when you display it."),
                h2("SQL you will use every day"),
                code(
                    "-- Which students have an overdue book right now?\n"
                    "SELECT s.full_name, b.title, l.due_at\n"
                    "FROM loans l\n"
                    "JOIN students s ON s.id = l.student_id\n"
                    "JOIN books    b ON b.id = l.book_id\n"
                    "WHERE l.returned_at IS NULL\n"
                    "  AND l.due_at < now()\n"
                    "ORDER BY l.due_at;",
                    "a join, a filter and an ordering",
                ),
                code(
                    "-- How many loans per student, including those with none?\n"
                    "SELECT s.full_name, count(l.id) AS loans\n"
                    "FROM students s\n"
                    "LEFT JOIN loans l ON l.student_id = s.id\n"
                    "GROUP BY s.id, s.full_name\n"
                    "ORDER BY loans DESC;",
                    "LEFT JOIN is what includes the zeroes",
                ),
                note(
                    "With a plain `JOIN`, students who have never borrowed anything "
                    "vanish from the result entirely. That is the difference between "
                    "'students and their loan counts' and 'students who have loans'."
                ),
                h2("Indexes: fewer than you think"),
                p(
                    "An index makes reads faster and writes slower, and takes disk. Add "
                    "one when you filter, join or sort by a column often. Do not add one "
                    "to every column on principle."
                ),
                p(
                    "The way to know is to ask the database. `EXPLAIN ANALYZE` in front "
                    "of a query prints the plan it actually used and how long each step "
                    "took. A `Seq Scan` over a large table in a query you run constantly "
                    "is your answer."
                ),
                code(
                    "EXPLAIN ANALYZE\n"
                    "SELECT * FROM loans WHERE student_id = 42 AND returned_at IS NULL;",
                    "measure before you add",
                ),
            ],
        ),
        Chapter(
            domain="Backend Development",
            number=2,
            title="HTTP APIs People Can Use",
            level="Intermediate",
            summary=(
                "An API is a contract with a developer you will never meet. "
                "This chapter is about the parts of that contract people get "
                "wrong: what the status code means, what happens when the "
                "caller is wrong, and how not to leak your database."
            ),
            minutes=40,
            outcomes=[
                "Choose the right status code without looking it up",
                "Validate input at the boundary with schemas",
                "Separate your API shape from your table shape, and know why",
                "Paginate and handle errors consistently",
            ],
            blocks=[
                h2("Status codes, decided once"),
                bullets(
                    "200 — here is what you asked for.",
                    "201 — I created something; the Location header says where.",
                    "204 — it worked and there is nothing to send back.",
                    "400 — the request is malformed in a way I cannot even parse.",
                    "401 — I do not know who you are. Authenticate and retry.",
                    "403 — I know who you are and the answer is still no.",
                    "404 — nothing lives at that path or that ID.",
                    "409 — this conflicts with the current state, such as a duplicate "
                    "email.",
                    "422 — well-formed, but a field failed validation.",
                    "500 — I have a bug. This is never the client's fault.",
                ),
                warn(
                    "The 401/403 distinction matters for the client's behaviour: on 401 "
                    "it should send the user to sign in; on 403 it must not, because "
                    "signing in again will change nothing and the loop is infuriating."
                ),
                h2("Validate at the boundary, once"),
                p(
                    "Define the shape of every request and response as a schema. Then "
                    "the framework rejects a bad request before your code runs, the "
                    "error message names the field, and your handler can assume its "
                    "input is well-formed."
                ),
                code(
                    "from pydantic import BaseModel, EmailStr, Field\n\n"
                    "class CreateLoan(BaseModel):\n"
                    "    book_id: int\n"
                    "    student_email: EmailStr\n"
                    "    days: int = Field(ge=1, le=30)\n\n"
                    "@app.post('/loans', status_code=201)\n"
                    "def create_loan(payload: CreateLoan):\n"
                    "    # payload.days is an int between 1 and 30. Guaranteed.\n"
                    "    ...",
                    "the validation you do not have to write",
                ),
                h2("Your tables are not your API"),
                p(
                    "Returning a database row directly is the fastest way to ship and "
                    "the fastest way to regret it. It leaks internal columns, couples "
                    "every client to your schema, and means a column rename is a "
                    "breaking API change."
                ),
                code(
                    "# Leaks password_hash, internal flags, and whatever you add next week.\n"
                    "return user\n\n"
                    "# Explicit, and safe to change the table underneath.\n"
                    "class UserOut(BaseModel):\n"
                    "    id: int\n"
                    "    full_name: str\n"
                    "    email: str\n"
                    "    model_config = {'from_attributes': True}\n\n"
                    "return UserOut.model_validate(user)",
                    "the response model is the contract",
                ),
                note(
                    "This is not theoretical. Adding an `is_internal_test_account` "
                    "column and having it appear in a public API response has happened "
                    "to most teams at least once."
                ),
                h2("Pagination, from the first endpoint"),
                p(
                    "Any list endpoint will eventually have more rows than anyone wants "
                    "to receive. Adding pagination later is a breaking change, so add it "
                    "at the start, when the table has four rows and it costs nothing."
                ),
                code(
                    "@app.get('/loans')\n"
                    "def list_loans(limit: int = Query(20, ge=1, le=100),\n"
                    "               offset: int = Query(0, ge=0)):\n"
                    "    rows = session.scalars(\n"
                    "        select(Loan).order_by(Loan.id).limit(limit).offset(offset)\n"
                    "    ).all()\n"
                    "    return {'items': rows, 'limit': limit, 'offset': offset}",
                    "note the upper bound on limit",
                ),
                p(
                    "The `le=100` matters. Without it, `?limit=10000000` is a denial of "
                    "service anyone can perform with a browser. The `order_by` matters "
                    "too: without a stable sort, paging through results can show you the "
                    "same row twice and skip another."
                ),
                h2("Errors clients can act on"),
                p(
                    "Pick one error shape and use it everywhere. A client that has to "
                    "parse three different error formats from the same API will parse "
                    "none of them and just show 'Something went wrong'."
                ),
                code(
                    "{\n"
                    '  "detail": "A loan already exists for this book",\n'
                    '  "code": "loan_conflict"\n'
                    "}",
                    "a machine-readable code, a human-readable message",
                ),
                warn(
                    "Never put the exception text in a production response. Stack traces "
                    "and SQL errors tell an attacker your table names, your library "
                    "versions and sometimes your file paths. Log them; return something "
                    "generic."
                ),
                key("Every 500 you return is a bug you have not fixed yet. Treat the count as a to-do list."),
                h2("Idempotency, briefly"),
                p(
                    "A client that times out does not know whether the request "
                    "succeeded. It will retry. If your POST creates a second loan, you "
                    "have a duplicate caused by a network blip. Accepting a client-"
                    "supplied idempotency key and returning the original result on a "
                    "repeat is the standard fix, and is worth doing for anything that "
                    "creates money, bookings or credentials."
                ),
            ],
        ),
        Chapter(
            domain="Backend Development",
            number=3,
            title="Auth, Testing and Running It for Real",
            level="Advanced",
            summary=(
                "Authentication done badly is the fastest way to end up in the "
                "news. This chapter covers doing it with standard parts, then "
                "the two things that decide whether your service survives "
                "contact with production: tests you trust, and logs you can use."
            ),
            minutes=45,
            outcomes=[
                "Store passwords so a database leak is not an account leak",
                "Issue and verify tokens, and revoke them when it matters",
                "Separate authentication from authorisation",
                "Write tests that fail for the right reasons",
            ],
            blocks=[
                h2("Passwords"),
                p(
                    "Never store a password. Store a verifier produced by a slow, salted "
                    "password hash — argon2 or bcrypt. Not SHA-256: it is designed to be "
                    "fast, and fast is exactly wrong here. A GPU will try billions of "
                    "SHA-256 guesses a second against a leaked table."
                ),
                code(
                    "from argon2 import PasswordHasher\n"
                    "from argon2.exceptions import VerifyMismatchError\n\n"
                    "hasher = PasswordHasher()\n\n"
                    "stored = hasher.hash(password)   # salted automatically\n\n"
                    "try:\n"
                    "    hasher.verify(stored, attempt)\n"
                    "except VerifyMismatchError:\n"
                    "    ...  # wrong password\n",
                    "four lines, and the library handles the salt",
                ),
                warn(
                    "Return the same error for 'no such email' and 'wrong password'. "
                    "Different messages let anyone enumerate which addresses have "
                    "accounts, which is a privacy leak before it is a security one."
                ),
                h2("Tokens, and what they cannot do"),
                p(
                    "A signed token carries claims the server can verify without a "
                    "database lookup. That property is the whole point and also the "
                    "whole problem: a token is valid until it expires, and nothing can "
                    "call it back."
                ),
                bullets(
                    "Keep access tokens short — minutes, not days.",
                    "Never put anything secret in the payload. It is base64, not "
                    "encryption; anyone can read it.",
                    "Never trust a role claim for authorisation. Look the user up and "
                    "read their current role from the database.",
                    "To make revocation possible, add a version number to the user row "
                    "and into the token, and compare them. Bump it on logout, password "
                    "change and account closure.",
                ),
                note(
                    "That last point is exactly how this platform does it. A password "
                    "reset increments the user's token version, so every token issued "
                    "before the reset stops working immediately — including the stolen "
                    "one that prompted the reset."
                ),
                h2("Authentication is not authorisation"),
                p(
                    "Authentication answers 'who is this'. Authorisation answers 'may "
                    "they do this'. They are separate checks and conflating them "
                    "produces the most common serious bug in web applications: a route "
                    "that checks you are logged in, and then acts on an ID from the URL "
                    "without checking it belongs to you."
                ),
                code(
                    "# Authenticated, and completely broken.\n"
                    "@app.get('/loans/{loan_id}')\n"
                    "def get_loan(loan_id: int, user = Depends(current_user)):\n"
                    "    return session.get(Loan, loan_id)   # anyone's loan\n\n"
                    "# Authorised: the ownership check is the query.\n"
                    "@app.get('/loans/{loan_id}')\n"
                    "def get_loan(loan_id: int, user = Depends(current_user)):\n"
                    "    loan = session.scalar(\n"
                    "        select(Loan).where(Loan.id == loan_id,\n"
                    "                           Loan.student_id == user.id)\n"
                    "    )\n"
                    "    if loan is None:\n"
                    "        raise HTTPException(404)\n"
                    "    return loan",
                    "IDOR, and the fix",
                ),
                p(
                    "Returning 404 rather than 403 for someone else's record is "
                    "deliberate: 403 confirms the record exists, which is information "
                    "the caller has not earned."
                ),
                key("Task 3 of this internship is graded on the test that proves user A cannot read user B's data. Write that test first."),
                h2("Tests worth having"),
                p(
                    "Coverage percentage is a poor target. The useful question is: if I "
                    "broke this on purpose, would a test fail? Write tests for the things "
                    "you would be embarrassed to ship broken — authorisation, money, "
                    "anything irreversible."
                ),
                code(
                    "def test_a_student_cannot_read_another_students_loan(client, db):\n"
                    "    alice, bob = make_student(db), make_student(db)\n"
                    "    loan = make_loan(db, student=alice)\n\n"
                    "    response = client.get(f'/loans/{loan.id}',\n"
                    "                          headers=auth_as(bob))\n\n"
                    "    assert response.status_code == 404",
                    "the test that would have caught the bug above",
                ),
                h2("Logs you can actually use"),
                p(
                    "Log events, not sentences. A line that says 'something went wrong' "
                    "is useless at 2am. A line carrying the request ID, the user ID, the "
                    "route and the outcome can be searched, counted and graphed."
                ),
                warn(
                    "Never log passwords, tokens, full card numbers or anything you "
                    "would not want in a text file read by a future colleague. Logs are "
                    "copied, shipped to third parties and kept longer than you expect."
                ),
                h2("A short production checklist"),
                steps(
                    "Secrets come from the environment and are absent from the "
                    "repository, including its history.",
                    "The service refuses to start on a placeholder secret.",
                    "Login and registration are rate limited.",
                    "Migrations run on deploy and have a tested downgrade.",
                    "There is a health endpoint, and something is watching it.",
                    "You have restored a backup at least once.",
                ),
            ],
        ),
    ],
)


# ===========================================================================
# Full Stack Web Development
# ===========================================================================

FULL_STACK = Stream(
    slug="full-stack-web-development",
    title="Full Stack Web Development",
    description=(
        "The whole path, from a Postgres table to a deployed interface. You "
        "will build one real application end to end — schema, API, frontend, "
        "authentication and deployment — and be reviewed on the seams between "
        "them, which is where full-stack work is actually hard."
    ),
    duration="8 weeks",
    difficulty="intermediate",
    icon="layers",
    display_order=0,
    skills=[
        "Python", "FastAPI", "PostgreSQL", "React", "TypeScript",
        "REST", "Authentication", "Deployment",
    ],
    outcomes=[
        "Take a feature from database column to rendered pixel",
        "Design an API contract and build both sides of it",
        "Handle auth end to end without storing a token where scripts can read it",
        "Deploy a full stack application and keep it running",
    ],
    tasks=[
        TaskSpec(
            order_number=1,
            title="A working vertical slice",
            description=(
                "Build one feature all the way through: a table, an endpoint, a "
                "screen, and a test at each layer. Narrow and complete beats "
                "broad and half-finished — a task manager with one entity done "
                "properly is the brief.\n\n"
                "What we are reading for is the seams. How does the frontend "
                "learn about a validation error? What does the screen show "
                "while the request is in flight? What happens if the API is "
                "down when the page loads?"
            ),
            requirements=[
                "Postgres schema created by a migration, not by hand",
                "API with validation and documented responses",
                "React frontend consuming it, with loading and error states",
                "One test per layer: a query test, an endpoint test, a component test",
                "README with a diagram of how a single request flows through",
            ],
            estimated_hours=16,
        ),
        TaskSpec(
            order_number=2,
            title="Accounts, sessions and ownership",
            description=(
                "Add authentication across the stack. Registration, sign-in, "
                "sign-out, and data that belongs to whoever created it.\n\n"
                "The part most people get wrong is the browser side. A token "
                "in localStorage can be read by any script that gets onto your "
                "page. Use httpOnly cookies, and be able to explain the "
                "trade-off you accepted when you did."
            ),
            requirements=[
                "Passwords hashed with argon2 or bcrypt",
                "Session held in an httpOnly cookie, not in localStorage",
                "Every record scoped to its owner, enforced in the query",
                "A test proving one user cannot read another's data",
                "Explanation covers your CSRF position and why it is sufficient",
            ],
            estimated_hours=16,
        ),
        TaskSpec(
            order_number=3,
            title="Deploy it, and make it observable",
            description=(
                "Put the whole application on the internet behind HTTPS, with "
                "the database somewhere real. Then make it possible to tell "
                "whether it is working without opening it.\n\n"
                "A deployment you cannot debug is not finished. We want a "
                "health endpoint, structured logs, and a short written answer "
                "to 'how would you know if this broke at 3am?'"
            ),
            requirements=[
                "Frontend, API and database all deployed and reachable over HTTPS",
                "Environment variables for every secret — none in the repository",
                "A health endpoint reporting real dependency status",
                "Logs that include a request identifier",
                "A written rollback procedure you have actually tested once",
            ],
            estimated_hours=14,
            require_live_demo=True,
        ),
    ],
    chapters=[
        Chapter(
            domain="Full Stack Web Development",
            number=1,
            title="How a Request Crosses the Stack",
            level="Beginner",
            summary=(
                "Full stack is not two jobs stapled together — it is owning the "
                "path a single request takes from a click to a row and back. "
                "This chapter follows one request the whole way and names every "
                "place it can go wrong."
            ),
            minutes=35,
            outcomes=[
                "Trace a request from browser to database and back",
                "Explain what the API contract is and who it binds",
                "Set up a local environment where both halves run together",
                "Debug across the boundary instead of guessing which side broke",
            ],
            blocks=[
                h2("One click, eight steps"),
                steps(
                    "A click handler runs and calls `fetch`.",
                    "The browser opens a connection and sends an HTTP request.",
                    "A reverse proxy terminates TLS and forwards it to your API.",
                    "The framework matches a route and validates the body.",
                    "Your handler runs a query; the driver turns it into SQL.",
                    "Postgres plans and executes it, returning rows.",
                    "The handler serialises a response the schema allows.",
                    "The browser parses the JSON and React re-renders.",
                ),
                p(
                    "Every one of those steps can fail, and each fails differently. "
                    "Being able to say which step produced the symptom is most of "
                    "debugging, and it is the skill this internship is really teaching."
                ),
                note(
                    "A quick triage: if the Network tab shows no request, it is step 1. "
                    "If it shows a 4xx, your request was wrong. A 5xx is the server's "
                    "bug. A CORS error is a browser refusing a response that did arrive."
                ),
                h2("The contract between the halves"),
                p(
                    "The API contract is the agreement about paths, request shapes, "
                    "response shapes and status codes. Both sides are built against it. "
                    "When it is written down, two people can work in parallel. When it "
                    "lives in someone's head, they cannot."
                ),
                code(
                    "POST /api/v1/tasks\n"
                    "  body     { title: string, due: string | null }\n"
                    "  201      { id: string, title: string, due: string | null }\n"
                    "  422      { detail: [{ field: string, message: string }] }\n"
                    "  401      { detail: string }",
                    "a contract, in four lines",
                ),
                p(
                    "Generate your types from this rather than writing them twice. "
                    "FastAPI publishes an OpenAPI document; tools turn it into "
                    "TypeScript. Two hand-maintained copies of the same shape will drift, "
                    "and the drift is found by a user."
                ),
                h2("Running both halves locally"),
                p(
                    "Two processes on two ports, and a browser that will not let them "
                    "talk to each other until you say so. That last part is CORS, and it "
                    "confuses everyone once."
                ),
                code(
                    "# terminal one\n"
                    "uvicorn app.main:app --reload --port 8000\n\n"
                    "# terminal two\n"
                    "npm run dev          # Vite on 5173\n",
                    "the normal setup",
                ),
                code(
                    "from fastapi.middleware.cors import CORSMiddleware\n\n"
                    "app.add_middleware(\n"
                    "    CORSMiddleware,\n"
                    "    allow_origins=['http://localhost:5173'],\n"
                    "    allow_credentials=True,\n"
                    "    allow_methods=['*'],\n"
                    "    allow_headers=['*'],\n"
                    ")",
                    "permission for the browser, not for the server",
                ),
                warn(
                    "`allow_origins=['*']` with `allow_credentials=True` is rejected by "
                    "browsers, and for good reason — it would let any site on the "
                    "internet make authenticated requests as your logged-in user. List "
                    "your origins explicitly."
                ),
                h2("Where the environment lives"),
                p(
                    "Anything that differs between your laptop and the server is "
                    "configuration: the database URL, the API base URL, secrets. It "
                    "belongs in the environment, never in the code, and the repository "
                    "should carry an example file listing every key with no real values."
                ),
                key("If cloning the repository and reading the example env file is not enough to run it, the README is incomplete."),
                h2("Debugging across the boundary"),
                p(
                    "When something breaks, find the boundary it broke at before "
                    "forming a theory. The Network tab tells you what the browser sent "
                    "and received. The server log tells you what arrived and what was "
                    "returned. Comparing the two settles most arguments in a minute."
                ),
                bullets(
                    "Request never appears — the bug is in your frontend code.",
                    "Request appears, 422 comes back — read the body; it names the field.",
                    "500 comes back — the server log has the traceback. Always look.",
                    "It works in curl but not the browser — CORS, cookies or headers.",
                ),
            ],
        ),
        Chapter(
            domain="Full Stack Web Development",
            number=2,
            title="State on Both Sides",
            level="Intermediate",
            summary=(
                "The server has the truth. The browser has a copy that is "
                "always slightly out of date. Most full-stack bugs are a "
                "disagreement between those two, and almost all of them are "
                "avoidable once you stop treating fetched data as state."
            ),
            minutes=40,
            outcomes=[
                "Distinguish server state from client state and handle each correctly",
                "Keep a cache coherent after a mutation",
                "Implement optimistic updates that roll back on failure",
                "Choose where validation belongs — which is both places",
            ],
            blocks=[
                h2("Two kinds of state"),
                bullets(
                    "Client state — is the menu open, what is typed in this box, which "
                    "tab is selected. Owned by the browser. Disappears on refresh, and "
                    "should.",
                    "Server state — the task list, the user's profile. Owned by the "
                    "database. The browser holds a copy that was true when it arrived.",
                ),
                p(
                    "Storing server state in `useState` and updating it by hand works "
                    "until two components need it, or until something changes in another "
                    "tab, or until a request fails halfway. Then you are writing a cache "
                    "by hand, badly, while believing you are writing application code."
                ),
                code(
                    "// A cache with staleness rules, in four lines.\n"
                    "const { data, isPending, error } = useQuery({\n"
                    "  queryKey: ['tasks'],\n"
                    "  queryFn: () => api.get('/tasks'),\n"
                    "});",
                    "loading and error states included, not invented",
                ),
                h2("After a write, the copy is wrong"),
                p(
                    "The moment you create a task, every cached list containing tasks is "
                    "stale. You have two honest options: ask for the data again, or "
                    "update the copy yourself. Doing neither is the bug where the new "
                    "item appears only after a refresh."
                ),
                code(
                    "const createTask = useMutation({\n"
                    "  mutationFn: (task) => api.post('/tasks', task),\n"
                    "  onSuccess: () => {\n"
                    "    // Simple, correct, one extra request.\n"
                    "    queryClient.invalidateQueries({ queryKey: ['tasks'] });\n"
                    "  },\n"
                    "});",
                    "refetch — the option to reach for first",
                ),
                h3("Optimistic updates, and the rollback"),
                p(
                    "For things that almost always succeed — a checkbox, a like — "
                    "showing the result immediately feels far better. The obligation you "
                    "take on is undoing it when the request fails, which is the half "
                    "people skip."
                ),
                code(
                    "useMutation({\n"
                    "  mutationFn: toggleDone,\n"
                    "  onMutate: async (id) => {\n"
                    "    await queryClient.cancelQueries({ queryKey: ['tasks'] });\n"
                    "    const previous = queryClient.getQueryData(['tasks']);\n"
                    "    queryClient.setQueryData(['tasks'], flip(id));\n"
                    "    return { previous };                 // kept for the rollback\n"
                    "  },\n"
                    "  onError: (_err, _id, context) => {\n"
                    "    queryClient.setQueryData(['tasks'], context.previous);\n"
                    "  },\n"
                    "  onSettled: () =>\n"
                    "    queryClient.invalidateQueries({ queryKey: ['tasks'] }),\n"
                    "});",
                    "the snapshot is the whole trick",
                ),
                warn(
                    "Never do this for anything irreversible or financial. A payment that "
                    "appears to have gone through and then silently reverses is worse "
                    "than a spinner."
                ),
                h2("Validate in both places, for different reasons"),
                p(
                    "Client validation is a courtesy: it tells someone their password is "
                    "too short before a round trip. Server validation is the actual "
                    "check, because anyone can send a request without going near your "
                    "form."
                ),
                key("Client validation is for the user's benefit. Server validation is for yours. You need both, and they must agree."),
                p(
                    "When they disagree, the user gets rejected by the server for "
                    "something the form accepted, with no way to understand why. Derive "
                    "both from one description of the rules where you can."
                ),
                h2("Sessions in the browser"),
                p(
                    "A token in `localStorage` is readable by every script on the page — "
                    "yours, your dependencies', and anything that manages to inject "
                    "itself. An httpOnly cookie is not readable by JavaScript at all, so "
                    "a cross-site scripting bug stops being an instant account takeover."
                ),
                p(
                    "The trade-off is that cookies are sent automatically, which is what "
                    "makes CSRF possible. `SameSite=Lax` handles the common cases; a "
                    "token on state-changing requests handles the rest."
                ),
                note(
                    "This platform routes browser requests through its own server "
                    "handlers, which hold the cookie and forward to the API. The JWT "
                    "never reaches client JavaScript at all. Task 2 asks you to do "
                    "something similar and explain the reasoning."
                ),
            ],
        ),
        Chapter(
            domain="Full Stack Web Development",
            number=3,
            title="Shipping and Keeping It Up",
            level="Advanced",
            summary=(
                "Running software is a different skill from writing it. This "
                "chapter covers getting a full stack application onto the "
                "internet, and the small number of things that decide whether "
                "you find out about a problem before your users do."
            ),
            minutes=40,
            outcomes=[
                "Deploy a frontend, an API and a database together",
                "Manage configuration and secrets safely",
                "Run migrations on deploy without fear",
                "Know what to log, what to watch, and how to roll back",
            ],
            blocks=[
                h2("What production adds"),
                bullets(
                    "TLS on everything, with certificates that renew themselves.",
                    "Secrets from the environment, never from the repository.",
                    "A migration step in the deploy, with a tested reverse.",
                    "Logs you can search, and a health endpoint something polls.",
                    "A backup, and at least one restore you have actually performed.",
                ),
                h2("Configuration"),
                p(
                    "One principle: the same build artefact runs in every environment, "
                    "and the environment supplies the differences. If your build embeds "
                    "the API URL, you need a separate build per environment and you will "
                    "eventually deploy the staging one to production."
                ),
                warn(
                    "Anything prefixed `NEXT_PUBLIC_` or `VITE_` is compiled into the "
                    "JavaScript and shipped to the browser. Putting a secret there is "
                    "publishing it. This has leaked real API keys for real companies."
                ),
                h2("Migrations on deploy"),
                p(
                    "Run them as part of starting the new version, and write the "
                    "downgrade at the same time as the upgrade. A migration you cannot "
                    "reverse is a deploy you cannot roll back."
                ),
                code(
                    "# In the service start command, before the server starts.\n"
                    "alembic upgrade head && uvicorn app.main:app --host 127.0.0.1\n",
                    "schema first, then traffic",
                ),
                p(
                    "For a change that would break the running version — dropping a "
                    "column it still reads — do it in two deploys. First stop using the "
                    "column, deploy, then drop it. Tedious, and the alternative is a "
                    "minute of 500s in the middle of the day."
                ),
                key("Take a database dump immediately before any deploy containing a migration. It costs seconds and it is the only real undo."),
                h2("Health checks that mean something"),
                code(
                    "@app.get('/health')\n"
                    "def health():\n"
                    "    try:\n"
                    "        session.execute(text('SELECT 1'))\n"
                    "    except Exception:\n"
                    "        raise HTTPException(503, 'database unreachable')\n"
                    "    return {'status': 'ok'}",
                    "checks a dependency, not just the process",
                ),
                p(
                    "An endpoint that returns 200 as long as the process is alive will "
                    "keep reporting healthy while every request fails on a dead database "
                    "connection. Check the thing that actually breaks."
                ),
                h2("Logging for the 3am case"),
                p(
                    "Attach a request ID at the edge and include it in every line that "
                    "request produces. When a student emails to say something failed, "
                    "that ID is how you find out what happened instead of guessing from "
                    "a timestamp."
                ),
                code(
                    'logger.info("submission_reviewed", extra={\n'
                    '    "request_id": request_id,\n'
                    '    "reviewer_id": str(admin.id),\n'
                    '    "submission_id": str(submission.id),\n'
                    '    "outcome": "approved",\n'
                    "})",
                    "an event, not a sentence",
                ),
                h2("Rolling back"),
                steps(
                    "Know the previous version's commit before you deploy.",
                    "Check out that commit and redeploy — this is the fast path.",
                    "If a migration ran and holds data, restore the pre-deploy dump "
                    "instead; a downgrade that drops a column drops what was in it.",
                    "Write down what happened the same day, while you still remember.",
                ),
                note(
                    "Task 3 asks you to test your rollback once, on purpose, before you "
                    "need it. Teams that skip this discover their rollback is broken "
                    "during the incident it was meant to fix."
                ),
            ],
        ),
    ],
)


STREAMS = [FULL_STACK, FRONTEND, BACKEND]
