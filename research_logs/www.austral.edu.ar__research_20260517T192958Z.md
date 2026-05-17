# Research Progress: PLAN CREATED

**Project: Operation Austral-Blueprint**
**Lead Archaeologist:** DOM-Digger
**Site:** `https://www.austral.edu.ar/`
**Initial Surface Scan:** 242 Components Detected.
**Objective:** Deconstruct the architectural DNA and state-driven logic of the Universidad Austral digital ecosystem.

---

### **Excavation Phase 1: Global Scaffolding & Hierarchy Mapping**
Before diving into the interactive depths, I will establish the primary skeletal nodes. This provides the "spatial" context for all sub-components.

1.  **Global Header Analysis:**
    *   **Node H1 (Utility Bar):** Map language toggles (ES/EN), access portals (Mi Austral), and top-level institutional links.
    *   **Node H2 (Primary Nav):** Identify the 5-7 core branches (e.g., *Carreras, Posgrados, Investigación, Sedes*).
    *   **Node H3 (Sticky State):** Monitor DOM mutations when scrolling to identify "Sticky Header" component transitions.
2.  **Global Footer Analysis:**
    *   **Node F1 (Sitemap Grid):** Extract all static link clusters.
    *   **Node F2 (Social/Trust signals):** Map external API handoffs (Facebook, LinkedIn, etc.).
    *   **Node F3 (Legal/Privacy):** Document the data contract nodes for privacy and terms.

---

### **Excavation Phase 2: Recursive Branching (The Mega-Menu Excavation)**
The "Carreras" and "Posgrados" menus are high-density interaction zones. I will treat these as "sub-applications."

1.  **Trigger Test (Hover/Click):** Determine if the mega-menus are DOM-present but hidden (CSS `display: none`) or DOM-injected on interaction (React/Vue/JS injection).
2.  **Branch Mapping:**
    *   **Carreras Branch:** Expand all categories (e.g., *Ciencias Biomédicas, Derecho, Ingeniería*).
    *   **Degree DNA:** For each degree node, document the "Action Path" (Link to sub-page vs. Quick-view modal).
3.  **Sedes (Campus) Logic:** Map the relationship between the "Sedes" dropdown and the geographic UI changes (Buenos Aires, Pilar, Rosario).

---

### **Excavation Phase 3: Stateful Interaction & Functional DNA**
I will now trigger every interactive element to observe the "Before → Action → After" state transitions.

1.  **The Search Engine (`#search-modal`):**
    *   **Trigger:** Click search icon.
    *   **Mutation:** Trace the modal overlay appearance.
    *   **Data Flow:** Type "Derecho" → Monitor XHR/Fetch requests to see if it’s a live-search API or a static redirect.
2.  **The "Consultas" (Inquiry) Funnel:**
    *   Locate floating "Contact" buttons or lead-gen forms.
    *   **Data Contract:** Document every form field (`input`, `select`, `textarea`) and the validation logic (client-side vs. server-side).
3.  **Dynamic Sliders/Hero Components:**
    *   Trace the `aria-live` regions and pagination dots to understand the auto-play logic and manual override triggers.

---

### **Excavation Phase 4: Route & Data Relationship Discovery**
I will map the underlying URL architecture to uncover "hidden" branches not explicitly linked in the main nav.

1.  **URL Pattern Extraction:**
    *   Structure A: `/carreras/[degree-name]/`
    *   Structure B: `/posgrados/[faculty]/[program]/`
2.  **Dependency Mapping:**
    *   Does selecting "Sede Pilar" filter the available "Carreras"? (State-driven dependency).
    *   Does the "Inscribite" button trigger an internal route or an external SaaS portal (e.g., Salesforce/Blackboard)?

---

### **Execution Schedule: The Deep Blueprint Output**

| Step | Action | Objective |
| :--- | :--- | :--- |
| **01** | **DOM Snapshotting** | Freeze the DOM in its initial, hovered, and scrolled states. |
| **02** | **Event Listener Audit** | Catalog all `click`, `mouseenter`, and `submit` events attached to the 242 components. |
| **03** | **Network Trace** | Log all JSON/Fetch calls triggered by interactive components to map the data-layer. |
| **04** | **Component DNA Synthesis** | Group the 242 components into functional families (Navigational, Informational, Transactional). |

**Ready to begin the first recursive crawl of the Primary Navigation Branch.**
*Awaiting authorization to deploy DOM-Digger sensors to the site header.*

---
