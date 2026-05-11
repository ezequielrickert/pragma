# Product Requirements Document: Universidad Austral Digital Ecosystem

## 1. Summary
This project involves the development and maintenance of the official web portal for **Universidad Austral (Argentina)**. The platform serves as a centralized hub for prospective and current students, faculty, and researchers to access academic programs, institutional information, and research resources across multiple campuses (CABA, Rosario) and online modalities.

## 2. Goals
*   **Centralize Information:** Provide a unified entry point for all regional campuses and online offerings.
*   **Drive Enrollments:** Implement a robust "Program Finder" to convert prospective students through filtered searches.
*   **Establish Authority:** Showcase global rankings, faculty prestige, and institutional sustainability efforts.
*   **Research Accessibility:** Integrate digital library services for academic excellence.

## 3. Users
*   **Prospective Students:** Domestic and international individuals seeking undergraduate or postgraduate programs.
*   **Current Students & Alumni:** Users looking for institutional news, library access, and campus-specific resources.
*   **Faculty & Researchers:** Staff seeking academic records, authority listings, and research databases.
*   **International Partners:** Visitors viewing the site in English to evaluate global rankings and prestige.

## 4. Key Features
*   **Multilingual Support:** Bi-directional toggle between Spanish (ES) and English (EN).
*   **Program Finder (Encontrá tu Programa):** Search engine with metadata filtering (e.g., Modality: Online/On-site).
*   **Campus Localization:** Dedicated landing pages for CABA and Rosario.
*   **Library Integration:** Search API integration with Primo (ExLibris Group) for bibliographic discovery.
*   **Institutional Repository:** Dedicated sections for "Memorias," "Rankings," and "Sustainability."

## 5. Page Breakdown
*   **Homepage:** Global navigation, hero section, and quick links to campuses.
*   **Institutional ("Quiénes Somos"):** 
    *   Authorities and Faculty profiles.
    *   Rankings and Accreditation showcase.
    *   Sustainability and Social Development reports.
*   **Academic Portal:**
    *   Searchable database of programs.
    *   Filtering by modality (Online/Hybrid/Face-to-face).
*   **Library (Biblioteca):**
    *   Direct integration with `uaustral.primo.exlibrisgroup.com`.
    *   Institutional memory and academic presentations.

## 6. Acceptance Criteria
*   **SEO & Metadata:** Must include `max-image-preview:large` and `hreflang` tags for proper regional indexing.
*   **Performance:** Implement lazy loading for all images (`min-height: 1px`) to optimize Core Web Vitals.
*   **Responsiveness:** UI must be mobile-first, ensuring accessibility on smartphones and tablets.
*   **Functional Search:** The program finder must correctly filter "Online" programs when the specific meta-attribute is selected.
*   **Legal/Compliance:** Must include robots.txt directives and secure RSS feeds for comments and posts.

## 7. Notes
*   **Tech Stack:** Built on WordPress using the **JetEngine** plugin for custom post types and dynamic listings.
*   **Performance Optimization:** W3 Total Cache is utilized for JS minification and asset delivery.