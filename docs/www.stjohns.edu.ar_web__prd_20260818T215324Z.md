> **Crawl coverage:** 0/85 pages (0%), 0/4677 components interacted with (0%), 1 API endpoints discovered.
>
> **This run stopped early:** page budget reached (21/20 pages). The pages it did not reach are still recorded as pending - run the same URL again to continue from there.
>
> Scope: the site's public surface. The crawl does not sign in, so any page or flow behind authentication is absent from this document and is not counted as missing below.

_(overview synthesis unavailable: Local API Error (400): {"error":"Engine protocol predict request returned 400: {\"error\":{\"code\":400,\"message\":\"request (36377 tokens) exceeds the available context size (4096 tokens), try increasing it\",\"type\":\"exceed_context_size_error\",\"n_prompt_tokens\":36377,\"n_ctx\":4096}}"})_

## Section 1

_(chunk combine unavailable: Local API Error (400): {"error":"Engine protocol predict request returned 400: {\"error\":{\"code\":400,\"message\":\"request (9177 tokens) exceeds the available context size (4096 tokens), try increasing it\",\"type\":\"exceed_context_size_error\",\"n_prompt_tokens\":9177,\"n_ctx\":4096}}"})_

## External Service Integration and Campus Resources

This section outlines a collection of external services and internal campus links that the application integrates with or directs users toward. These pages primarily facilitate communication, external access, and specific institutional resources.

### Summary

The listed pages serve three main functions: WhatsApp API interaction for external messaging, access to the institutional virtual campus, and integration with Facebook services.

*   **WhatsApp Messaging APIs:** Three distinct endpoints are dedicated to interfacing with the WhatsApp API (`api.whatsapp.com/send/?phone=...`). These endpoints suggest functionality for initiating messages or contact actions using specific phone numbers.
*   **Campus Virtual Access:** The route `campusvirtual.stjohns.edu.ar` provides external access to the St. John's University virtual campus resources.
*   **Social Media Integration:** The dynamic link `facebook.com/{token}` is used for interfacing with Facebook, likely involving authenticated actions or content sharing via a provided token.

In summary, this group of pages manages outbound communication (via WhatsApp), institutional navigation (campusvirtual), and social media interaction (Facebook).

## External & Internal Services Summary

This section documents a collection of pages that serve both external resource links and specific internal account access points on the stjohns.edu.ar domain.

**External Links:**
The following pages provide external resources:
*   A link to Google Maps (`goo.gl/maps/NbjUq3Gvsgw`).
*   An external link to Instagram (`instagram.com/{token}`).

**Internal Account & Communication Services:**
These pages manage user access and communication functions within the site:
*   **Film Festivals Account Login:** Provides access for users related to Film Festivals (`legajos.stjohns.edu.ar/FilmFestivals/Account/Login`).
*   **Parents Account Login:** Provides access for parents to manage their accounts (`legajos.stjohns.edu.ar/Padres/Account/Login`).
*   **Mail Service:** Provides access to the site's mail functionality (`mail.stjohns.edu.ar/index.php`).

In summary, this group of pages provides entry points for external navigation and specific user authentication related to site features (Film Festivals, Parents) alongside general communication tools.

## Digital Blueprint: Admissions and Institutional Information

This section of the website provides external geographical context and serves as the primary hub for educational admissions, institutional history, and application processes for St. John's school. The content is structured around guiding prospective parents through the admission lifecycle.

### 1. External Location Context (Google Maps Links)

The site includes three external links to Google Maps, providing geographical context for the school's locations in Buenos Aires:
*   St. John's Beccar
*   St. John's Martinez
*   St. John's Pilar

### 2. Calendario (Admission Calendar)

**Route:** `/Web/Admision/Calendario`
**Description:** This page functions as a comprehensive calendar and informational hub for admissions, detailing the current academic cycle and institutional facts.

**Key Functions:**
*   **Institutional Information:** Links provide details on the school's history (`Nuestra Historia`), institutional structure (`El Colegio`, `Institucional`), educational focus areas (Artística, Científica, Humana), and community information.
*   **Educational Structure:** Specific links detail programs for Kindergarten, Primary Education, and Secondary Education.
*   **Actionable Steps:** It provides direct links to initiate the admission process (`Iniciar proceso`), view schedules (`Calendario`), request interviews (`Solicitar entrevista`), and download necessary documents (brochures).
*   **External Resources:** Links are provided to external platforms like Moodle and Webmail.

### 3. Entrevista (Interview/Application Process)

**Route:** `/Web/Admision/Entrevista`
**Description:** This page focuses specifically on the interactive stages of the application process, linking directly to the necessary steps and supporting documentation.

**Key Functions:**
*   **Application Workflow:** It reinforces the admission path by providing links related to parents' records (`Padres - Legajos`), starting the application (`Iniciar proceso`), and managing interviews (`Entrevista`).
*   **Institutional Context (Repetition):** Similar to the Calendar page, it includes extensive institutional details, including history, programs, and community information.
*   **Interactive Elements:** The interface includes interactive elements such as tab selection (MADRE, PADRE, POSTULANTE) and a selection dropdown, suggesting an interactive way for users to navigate application-related data.

### Summary of Relationship

The **Calendario** page serves as the high-level overview of institutional facts and the overall timeline of the admission cycle. The **Entrevista** page drills down into the specific actions required within that cycle (application steps, interview scheduling) while retaining access to the core school information provided by the Calendar. Together, these pages create a complete resource for prospective families seeking both educational details and application guidance.

## Admissions Process & Academic Calendar Overview

This section of the website is dedicated to guiding prospective students through the admissions process, providing detailed information about school levels, academic programs, and scheduling. The pages are tightly integrated, allowing users to initiate an application, view the relevant academic calendar, and manage interview requests.

### Page Summary

#### 1. Iniciar proceso (`/Web/Admision/Iniciar-proceso`)
This page serves as the central action point for starting the admission inquiry. It informs the user that upon submission of their request, the admissions secretary will contact them by phone to coordinate an interview. The process involves meetings with school leadership and the admissions secretariat at the desired location. Key elements include links for navigation across school levels (Kinder, Primaria, Secundaria), application actions (Iniciar proceso), scheduling (Entrevista), and contact information.

#### 2. Calendario (`/Web/Admision/calendario`)
This page provides the context for the academic cycle, serving as the **Current Academic Year Calendar**. It links all relevant admissions and institutional information together.

**Key Functions:**
*   **Navigation:** Provides structured links to educational levels (Kindergarten, Primary, Secondary), academic focus areas (Artística, Científica, Deportiva, Humana), and institutional details (Nuestra Historia, Convenios).
*   **Process Links:** Offers direct links for starting the admission process, viewing interview information, and downloading brochures.
*   **Community & Administration:** Includes links related to alumni, parent records (`Padres - Legajos`), Moodle access, and webmail services.

### Integration and Flow

The two primary pages work together to create a cohesive admissions experience:

1.  A user starts by reviewing the **Calendar** page (`/Web/Admision/calendario`) to understand the academic structure, available programs, and timelines for the current cycle.
2.  From this overview, the user can navigate through the structured links (e.g., Primaria, Secundaria) or initiate the formal application process via the **Iniciar proceso** page (`/Web/Admision/Iniciar-proceso`).
3.  The final step involves scheduling interviews, which is facilitated through the links provided on both pages.

In essence, these pages combine institutional information and academic structure with actionable steps to facilitate student enrollment inquiries.

## Digital Blueprint: Admissions and Institutional Information

This section of the website focuses on providing prospective students, parents, alumni, and the community with comprehensive information regarding St. John's School admissions, academic programs, institutional history, and community engagement. The pages are designed to guide users through the entire journey, from initial inquiry to application and post-school connection.

### Core Functions

The linked pages collectively serve three main functions:

1.  **Admissions Process:** Providing all necessary steps, schedules, forms, and contact points for applying to the school.
2.  **Institutional & Academic Details:** Offering deep dives into the school's history, structure (Kindergarten, Primary, Secondary), administrative details, and specialized academic areas.
3.  **Community & Alumni Engagement:** Connecting users with information about the school community, alumni resources, and institutional values.

### Page Interconnectivity

The pages are structured to facilitate a seamless user experience, allowing users to navigate between informational topics and actionable steps:

*   **Starting the Journey (Admissions):** The flow begins with general admissions information (`/Web/Admissions/Start-Process`) and specific action links like scheduling an interview (`/Web/Admissions/Interview`) or viewing the academic calendar (`/Web/Admissions/calendar`).
*   **Contextual Information:** Users can access detailed structural information (School Levels, Academic Areas) and historical context (`Our History`, `Agreements`, `Institutional` details) alongside the application process.
*   **Community Focus:** Dedicated pages (`/Web/Alumni/Community`) provide specific resources for former students and community members, linking back to the core institutional identity.
*   **System Access:** All sections are supported by links to internal systems for resource access (Moodle, Webmail) and multilingual support (English and Español).

### Key Content Areas

The website is organized around the following major thematic areas:

*   **School Levels:** Detailed information covering Kindergarten, Primary School, and Secondary School.
*   **Academic Offerings:** Information on specific curriculum areas such as Arts, Science, Sports, Social Skills, and Educational Proposals.
*   **Institutional History:** Details regarding the school's history, agreements, and institutional structure.
*   **Application & Contact:** Tools for initiating applications, downloading brochures, scheduling meetings, and accessing parent records (`Padres - Legajos`).
*   **Community Resources:** Links dedicated to alumni stories and community involvement.

_(section summary unavailable: Response truncated: the model hit max_tokens before finishing (finish_reason: 'length'). This is almost always max_tokens set too low for a reasoning model's chain-of-thought - raise agents.local.max_tokens (or LOCAL_MAX_TOKENS) in pragma.yaml/.env and try again, or unset it entirely to let the model use as much as it needs.)_

- stjohns.edu.ar/Web/Alumni/Have-You-Heard [Scouted, 170 components]
  Description: ¿Sabías qué? - Las historias de nuestros exalumnos se actualizan mensualmente.
Si querés recibir la newsletter por favor escribinos a news@stjohns.edu.ar
  Components:
## Page Navigation and School Information

This section groups the interactive elements based on their function within the page structure.

### Global Controls
*   **Close Button:** Closes the current view or modal.
*   **Toggle navigation:** Controls the visibility of the main navigation menu.

### Main Navigation Links
These links provide access to major sections of the website:
*   Admissions
*   Kinder
*   Primary
*   Secondary
*   Admissions (Repeated link)

### Institutional Information and History
This group relates to general information about the school and its context:
*   The School
*   Institutional details
*   Our History
*   Agreements
*   Sites And Contacts

### Educational Programs and Subjects
Links providing access to specific academic areas:
*   Integral Formation
*   Academics
*   Arts
*   Science
*   Sports
*   Social Skills
*   Educational Project
*   Educational Proposal
*   Kindergarten
*   Primary School
*   Secondary School

### Alumni and Contact Resources
Links providing resources for former students and contact information:
*   Work with us. Send CV
*   Padres - Legajos (Parents - Records)
*   Moodle
*   Webmail
*   Have you heard (Link 1)
*   Have You Heard (Link 2)
*   Alumni
*   Community
*   Sites And Contacts

### Application and Process Links
Links guiding users through the application process:
*   Admission
*   Start Process
*   Interview
*   Calendar
*   Download Brochure

### Language Options
*   EN (English)
*   Español
*   English

### Alumni Contact/Record Links
A list of specific alumni entries, likely providing contact or record links:
*   news@stjohns.edu.ar
*   CLARA BENADIBA (2017)
*   FRANCISCO BOSCH (1983)
*   IVÁN CUENCA (1998)
*   RODRIGO TEIJEIRO (1995)
*   MARCOS MAFÍA DEL CASTILLO (2006)
- stjohns.edu.ar/Web/Alumni/Sabias-Que [Scouted, 168 components]
  Description: ¿Sabías qué? - Las historias de nuestros exalumnos se actualizan mensualmente.
Si querés recibir la newsletter por favor escribinos a news@stjohns.edu.ar
  Components:
## Navigation and Menu Links

### Admissions and Educational Levels
This section contains links related to admissions processes and educational stages:
*   **Admisiones:** Links related to admissions procedures.
*   **Kinder:** Links pertaining to Kindergarten.
*   **Primaria (Primer ciclo):** Links related to Primary education (first cycle).
*   **Educación Primaria:** Links related to Primary education.
*   **Educación Secundaria:** Links related to Secondary education.
*   **Secundaria:** Links related to Secondary education.

### Alumni and Community Information
This section provides links for alumni, community information, and general school context:
*   **Alumni:** Link related to alumni information.
*   **Comunidad:** Link related to the school community.
*   **Nuestra Historia:** Link providing the school's history.
*   **Proyecto Educativo:** Link to the educational project details.
*   **Propuesta Educativa:** Link to the educational proposal.

### Academic and Subject Areas
Links detailing academic focus areas:
*   **Académica:** Link related to academic information.
*   **Artística:** Link related to artistic subjects.
*   **Científica:** Link related to scientific subjects.
*   **Deportiva:** Link related to sports/physical education.
*   **Humana:** Link related to humanities subjects.

### Contact and Institutional Links
Links providing institutional details, contact information, and external resources:
*   **Sedes y Contacto:** Link for locations and contact information.
*   **Webmail:** Link to webmail services.
*   **Moodle:** Link to Moodle platform.
*   **St. John's School:** Link to the main school page.

### Informational Links
Links offering general information or specific resources:
*   **¿Sabías qué?:** Links containing trivia or interesting facts.
*   **Convenios:** Link related to agreements or partnerships.
*   **Padres - Legajos:** Link for parents' records.
*   **Entrevista:** Link for interviews.
*   **Calendario:** Link to the school calendar.
*   **Descargar Folleto:** Link to download a brochure.

### Language Options
Links allowing navigation or content in different languages:
*   **Español**
*   **English**

## Action Buttons

*   **Close:** A button used to close an interface element.
*   **Toggle navigation:** A button used to toggle the visibility of the main navigation menu.
- stjohns.edu.ar/Web/El-Colegio/Convenios [Scouted, 61 components]
  Description: CONVENIOS Y ALIANZAS - Promovemos lazos y convenios con las principales instituciones educativas de habla inglesa, manteniendo un nivel de formación bajo los más altos estándares mundiales. Contamos con convenios con las más prestigiosas universidades privadas nacionales para el ingreso directo de n
  Components:
## Navigation and Main Sections

*   **Toggle navigation:** A button used to toggle the main navigation menu visibility.
*   **El Colegio:** Link leading to information about the school itself.
*   **Institucional:** Link leading to institutional information about the school.
*   **Nuestra Historia:** Link providing the school's history.
*   **Convenios:** Link related to agreements or partnerships.
*   **Sedes y Contacto:** Link providing location and contact information.
*   **¿Sabías qué?:** Link to interesting facts or trivia.

## Academic Programs and Levels

This section contains links to various educational levels:

*   **Admisiones:** Link for admissions information.
*   **Kinder:** Link related to Kindergarten programs.
*   **Primaria:** Link related to Primary education.
*   **Secundaria:** Link related to Secondary education.
*   **Primaria (Primer ciclo):** Link specifically for the Primary cycle.
*   **Educación Primaria:** Link related to Primary education.
*   **Educación Secundaria:** Link related to Secondary education.
*   **Kindergarten:** Link related to Kindergarten.

## Admission and Process Links

*   **Admisión (x3):** Links related to the admission process.
*   **Iniciar proceso:** Link to start an application or admission process.
*   **Entrevista:** Link related to scheduling or information about interviews.
*   **Calendario:** Link to view the school calendar.
*   **Descargar Folleto:** Link to download a brochure or leaflet.

## Institutional and Contact Information

*   **Padres - Legajos:** Link likely directing parents to records or files.
*   **Moodle:** Link to the Moodle learning management system.
*   **Webmail:** Link to access the school's webmail service.
*   **ES:** Link related to Spanish language resources.
*   **Español:** Link to Spanish language content.
*   **English:** Link to English language content.

## Curriculum and Focus Areas

Links detailing the focus areas of the education offered:

*   **Formación Integral:** Link regarding integral education.
*   **Académica:** Link related to academic aspects.
*   **Artística:** Link related to artistic education.
*   **Científica:** Link related to scientific education.
*   **Deportiva:** Link related to physical education.
*   **Humana:** Link related to humanistic education.
*   **Proyecto Educativo:** Link to the educational project details.
*   **Propuesta Educativa:** Link to the proposed educational approach.

## Alumni and Community

*   **Alumni:** Link for former students or alumni information.
*   **Comunidad:** Link related to the school community.

## Partnerships and Diplomas (Custom Controls)

This section lists links related to specific international partnerships or diplomas:

*   **IB DIPLOMA (x2):** Custom control link referencing the IB Diploma program.
*   **ALIANZA FRANCESA (x2):** Custom control link referencing the French Alliance.
*   **UNIVERSIDAD DE SAN ANDRÉS (x2):** Custom control link referencing the University of San Andrés.
*   **UNIVERSIDAD TORCUATO DI TELLA (x2):** Custom control link referencing the University of Torcuato di Tella.
*   **UNIVERSIDAD AUSTRAL:** Custom control link referencing the University of Austral.
- stjohns.edu.ar/Web/El-Colegio/Institucional [Scouted, 57 components]
  Description: ST. JOHN'S SCHOOL - Desde 1950 hemos educado a más de tres generaciones de argentinos, proveyéndolos de una sólida y distintiva formación.
  Components:
## Navigation and Main Links

*   **Toggle navigation:** A button used to open or close the main navigation menu.
*   **El Colegio:** Link to the main school page.
*   **Institucional:** Link to institutional information about the school.
*   **Nuestra Historia:** Link providing the school's history.
*   **Convenios:** Link detailing agreements and partnerships.
*   **Sedes y Contacto:** Link for finding locations and contact information.

## Admissions and School Levels

This section contains links related to admissions processes and educational levels:

*   **Admisiones:** Link related to admissions procedures. (Appears multiple times)
*   **Kinder:** Link related to Kindergarten. (Appears multiple times)
*   **Primaria:** Link related to Primary education. (Appears multiple times)
*   **Secundaria:** Link related to Secondary education. (Appears multiple times)
*   **Primaria (Primer ciclo):** Link specifically for the Primary (First cycle).

## Educational Focus Areas

Links detailing the school's educational philosophy and focus areas:

*   **Formación Integral:** Information regarding integral education.
*   **Académica:** Information about the academic aspects.
*   **Artística:** Information about artistic education.
*   **Científica:** Information about scientific education.
*   **Deportiva:** Information about sports/physical education.
*   **Humana:** Information about humanistic education.
*   **Proyecto Educativo:** Details about the educational project.
*   **Propuesta Educativa:** Details about the educational proposal.

## School Information and Resources

*   **St. John's School:** Link to general information about the school.
*   **Padres - Legajos:** Link for parents to access records.
*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to the webmail service.
*   **¿Sabías qué?:** Links providing trivia or interesting facts. (Appears multiple times)
*   **Alumni:** Information for former students.
*   **Comunidad:** Information about the school community.

## Actions and Documents

Links that initiate specific processes or provide resources:

*   **Admisión:** Link related to the admission process.
*   **Iniciar proceso:** Link to start a formal process.
*   **Entrevista:** Link related to scheduling an interview.
*   **Calendario:** Link to the school calendar.
*   **Descargar Folleto:** Link to download a brochure.

## Language Options

*   **ES:** Link for Spanish language content.
*   **Español:** Link for Spanish language content.
*   **English:** Link for English language content.

## Other Links

*   **Web:** Link labeled "Web".
*   **Sedes y contacto:** Another link for locations and contact details.
- stjohns.edu.ar/Web/El-Colegio/{token} [Scouted, 63 components]
  Description: Nuestra historia - La relación entre un alumno y su colegio no termina el último día de clases. El lugar y las personas que contribuyeron a la formación de un individuo pasan a formar parte de él.
  Components:
## Navigation and Page Flow

This section describes components used for navigating between pages or sections of the current view.

*   **Previous/Next Links:** Standard navigation links labeled "Previous" and "Next," likely used to move sequentially through content.
*   **Toggle Navigation Button:** A button labeled "Toggle navigation," typically used to show or hide a main menu.

## School Information and History

This section includes links providing details about the school, its history, and organizational structure.

*   **School Identity:** A link labeled "St. John's School."
*   **School Sections:** Links leading to general information such as "El Colegio" and "Institucional."
*   **History and Partnerships:** Links for viewing "Nuestra Historia" (Our History) and "Convenios" (Agreements).
*   **Contact and Locations:** A link for "Sedes y Contacto" (Locations and Contact) is present multiple times.
*   **FAQs:** A link labeled "¿Sabías qué?" (Did you know?) is available.

## Educational Programs and Curriculum

These links categorize the school's educational offerings.

*   **Educational Levels/Cycles:** Links for various educational stages, including "Kinder" (Kindergarten), "Primaria" (Primary), and "Secundaria" (Secondary).
*   **Curriculum Focus Areas:** Links detailing specific educational focus areas: "Formación Integral" (Integral Education), "Académica" (Academic), "Artística" (Artistic), "Científica" (Scientific), "Deportiva" (Sports), and "Humana" (Humanities).
*   **Educational Proposals:** Links for viewing the school's specific educational plans, such as "Proyecto Educativo" and "Propuesta Educativa."

## Admissions and Enrollment

This group contains links related to the application process and enrollment information.

*   **Admissions Information:** Multiple links labeled "Admisiones" (Admissions) are present, likely leading to different admission procedures or requirements.
*   **Application Steps:** Links guiding users through the application process: "Admisión," "Iniciar proceso" (Start process), and "Entrevista" (Interview).
*   **Admission Details:** Links for specific educational entry points, including "Kindergarten," "Educación Primaria," and "Educación Secundaria."
*   **Alumni and Community:** Links related to the school's community: "Alumni" and "Comunidad" (Community).

## Administrative and External Resources

These components link to administrative documents, external systems, and specific data.

*   **Documents:** A link to "Descargar Folleto" (Download Brochure) is available.
*   **Records Access:** A link labeled "Padres - Legajos" (Parents - Records) allows access to records.
*   **External Systems:** Links leading to external platforms like "Moodle" and "Webmail."
*   **Language Options:** Links allowing the viewing of content in different languages: "ES" (Spanish), "Español," and "English."

## Data/Timeline Tabs

*   **Year Tabs:** Two tabs labeled "1950" and "1960," likely used to switch between historical timelines or data sets.

## Hidden Fields

Several text fields are present on the page that do not display accessible labels, suggesting they may be used for internal data processing or filtering.

_(section summary unavailable: Response truncated: the model hit max_tokens before finishing (finish_reason: 'length'). This is almost always max_tokens set too low for a reasoning model's chain-of-thought - raise agents.local.max_tokens (or LOCAL_MAX_TOKENS) in pragma.yaml/.env and try again, or unset it entirely to let the model use as much as it needs.)_

- stjohns.edu.ar/Web/Sedes-Contacto [Scouted, 78 components]
  Description: SEDES Y CONTACTO - Panamericana Km. 48.800
  Components:
## Navigation and School Information

This section contains links for navigating the website, accessing institutional information, and viewing school locations.

*   **Toggle navigation:** Controls the visibility of the main navigation menu.
*   **El Colegio:** Link to information about the school body/structure.
*   **Institucional:** Link to general institutional information.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Convenios:** Link for viewing agreements or partnerships.
*   **Sedes y Contacto (Locations and Contact):** Links related to finding school locations and contact details.
*   **¿Sabías qué?:** Links to general informational content.

## Academic Programs

This section links to various educational programs offered by the school.

*   **Kindergarten:** Link related to kindergarten programs.
*   **Educación Primaria (Primary Education):** Link related to primary education.
*   **Educación Secundaria (Secondary Education):** Link related to secondary education.
*   **Primaria (Primer ciclo) (Primary - First Cycle):** Link specifically for the first cycle of primary education.
*   **Académica:** Link related to academic aspects.
*   **Artística:** Link related to artistic programs.
*   **Científica:** Link related to scientific programs.
*   **Deportiva:** Link related to sports programs.
*   **Humana:** Link related to humanities programs.
*   **Proyecto Educativo (Educational Project):** Link detailing the educational project.
*   **Propuesta Educativa (Educational Proposal):** Link detailing the educational proposal.

## Admissions and Enrollment

This section provides links related to the admission process, application, and required documentation.

*   **Admisiones (Admissions):** Links related to the admissions process for various levels.
*   **Iniciar proceso (Start Process):** Link to begin an application process.
*   **Entrevista (Interview):** Link related to scheduling or information about interviews.
*   **Calendario (Calendar):** Link to view relevant dates.
*   **Descargar Folleto (Download Brochure):** Link to download a brochure.
*   **Admisión:** General link related to admission procedures.
*   **Padres - Legajos (Parents - Records):** Link related to parent records or files.
*   **Trabajar en St. John's. Enviar CV (Work at St. John's. Send CV):** Link for job applications or sending a CV.

## Community and Alumni

Links focused on the school community and alumni relations.

*   **Alumni:** Link for alumni information.
*   **Comunidad (Community):** Link related to the school community.

## Language Options

Links allowing users to view content in different languages:

*   **ES (Spanish)**
*   **Español (Spanish)**
*   **English**

## Contact and External Links

Links providing specific contact methods and external mapping services.

*   **Ver en Google Maps (View on Google Maps):** Link to view locations on Google Maps.
*   **Whatsapp admisiones (WhatsApp admissions):** Link for contacting admissions via WhatsApp.
- stjohns.edu.ar/Web/Sites-Contacts [Scouted, 79 components]
  Description: SITES AND CONTACTS - Panamericana Km. 48.800
  Components:
## Navigation and School Information Links

This section groups links related to school admissions, educational levels, administrative information, and institutional details.

### Admissions and Enrollment Links
These links guide users through the process of applying or seeking information about enrollment.

*   **Admissions:** Links related to school admission processes (appears multiple times).
*   **Kinder:** Links providing information specific to Kindergarten programs.
*   **Primary:** Links relating to primary school information, including "Primary (First cycle)".
*   **Secondary:** Links relating to secondary school information.
*   **Admission:** General links related to the admission process.
*   **Start Process:** A link to begin an application or process.
*   **Interview:** A link related to scheduling or accessing interview information.

### Academic and Subject Links
These links direct users to specific academic areas or educational offerings.

*   **Academics:** Information regarding the school's academic structure.
*   **Arts:** Information related to the Arts curriculum.
*   **Science:** Information related to the Science curriculum.
*   **Sports:** Information related to sports programs.
*   **Social Skills:** Information related to social skills development.

### Institutional and History Links
These links provide background information about the school and its structure.

*   **The School:** General information about the institution.
*   **Institutional:** Information regarding the school's institutional details.
*   **Our History:** Information detailing the school's history.
*   **Agreements:** Information concerning formal agreements.
*   **Sites And Contacts:** Links related to finding websites and contact information (appears multiple times).

### Contact, Media, and External Resources
These links facilitate communication, external access, and resource downloads.

*   **Work with us. Send CV:** A link for potential employees or those wishing to submit a curriculum vitae.
*   **Padres - Legajos:** A link potentially for parents or official records.
*   **Moodle:** A link to the Moodle learning platform.
*   **Webmail:** A link related to school email services.
*   **Download Brochure:** A link to download a brochure.
*   **Calendar:** Access to the school calendar.
*   **View in Google Maps:** A link to view the location on Google Maps.
*   **Send email:** A link for sending an email.

### Language Links
These links allow users to switch the language of the page.

*   **EN:** Link to the English version.
*   **Español:** Link to the Spanish version.
*   **English:** Link to the English version (appears alongside EN).
- stjohns.edu.ar/Web/The-School/Agreements [Scouted, 63 components]
  Description: AGREEMENTS AND JOINT VENTURES - We have established ties with the main English speaking educational institutions and share sports and cultural activities with them. Our academic standards are in accordance with the highest world standards. Agreements signed with prestigious, private Argentine univer
  Components:
## Navigation and Admissions Links

This section groups links related to school admissions, educational levels, and general institutional information.

### School Levels & Admissions
Links related to different stages of schooling and admission processes:
*   **Admissions:** General link for admissions information.
*   **Kinder:** Information regarding Kindergarten programs.
*   **Primary:** Information regarding Primary education.
*   **Secondary:** Information regarding Secondary education.
*   **Primary (First cycle):** Specific details about the first cycle of primary school.

### Academic and Program Areas
Links detailing the scope of the school's academic offerings:
*   **Academics:** Information on the school's academic structure.
*   **Arts:** Information related to the Arts curriculum.
*   **Science:** Information related to the Science curriculum.
*   **Sports:** Information related to Sports programs.
*   **Social Skills:** Information related to Social Skills development.
*   **Integral Formation:** Information on integral formation.
*   **Educational Project:** Information about educational projects.
*   **Educational Proposal:** Information regarding educational proposals.

### Institutional and History Links
Links providing background, history, and contact information:
*   **The School:** General information about the school.
*   **Institutional:** Information about the institution itself.
*   **Our History:** The school's history.
*   **Agreements:** Documentation regarding agreements.
*   **Sites And Contacts:** Links providing site information and contact details.

### Specific Resources and Actions
Links offering specific resources, contact methods, or calls to action:
*   **Have you heard:** A link prompting further inquiry (context dependent).
*   **Webmail:** Access to webmail services.
*   **Moodle:** Link to the Moodle platform.
*   **Padres - Legajos:** A section likely related to parent records or files.
*   **Work with us. Send CV:** A link for job applications or sending a CV.
*   **Interview:** Information or access related to interviews.
*   **Calendar:** Access to the school calendar.
*   **Download Brochure:** Link to download a brochure.

### Language Options
Links allowing users to switch the language of the page:
*   **EN:** English language option.
*   **Español:** Spanish language option.
*   **English:** Another link for the English language.

## Custom Selection Controls (Diplomas/Universities)

This section contains custom controls likely used for selecting specific diploma types or associated universities.

### Diploma/Institution Selections
Controls allowing selection of specific educational qualifications:
*   **IB DIPLOMA:** A selection option related to the IB Diploma.
*   **ALLIANCE FRANÇAISE:** A selection option related to the Alliance Française.
*   **SAINT ANDREWS´S UNIVERSITY:** A selection option related to Saint Andrews University.
*   **TORCUATO DI TELLA UNIVERSITY:** A selection option related to Torcuato di Tella University.
- stjohns.edu.ar/Web/The-School/Institutional [Scouted, 59 components]
  Description: ST. JOHN'S SCHOOL - We have been at the forefront of private education in Argentina for more than three generations.
  Components:
## Navigation and School Structure

This section contains links for navigating different sections of the school's institutional information, covering admissions, educational levels, history, and contact details.

*   **Admissions & Enrollment:** Links related to the application process, including general admissions, kindergarten, primary, and secondary school information.
*   **Institutional Information:** Links providing details about the school, such as our history, agreements, sites and contacts, and specific links for alumni and community information.
*   **Academic Areas:** Links detailing the curriculum and academic focus areas, including Academics, Arts, Science, Sports, and Social Skills.

## School Details and Resources

This section provides specific links related to school administration, historical context, and available resources.

*   **School Identity & History:** Links such as "St. John's School," "Our History," and information regarding agreements.
*   **Admissions Process:** Links for starting the application process, interviewing, and downloading brochures.
*   **Administrative & Contact Information:** Links providing access to administration details, parent records ("Padres - Legajos"), Moodle, Webmail, and general sites and contacts.

## Language Options

Links allowing users to view content in different languages:

*   English
*   Español

## General Navigation Controls

*   **Toggle navigation:** A button used to control the display of the main navigation menu.
- stjohns.edu.ar/Web/The-School/Our-History [Scouted, 65 components]
  Description: OUR HISTORY - The bond between a student and the school does not end on his or her graduation day. The place and the people who contributed to his or her growth live within him or her.
  Components:
## Navigation and History Controls

This section includes controls for navigating through historical content and general page movement.

*   **Previous / Next:** Links used to navigate between pages or sections of content.
*   **Year Tabs:** Tabs allowing navigation between specific years, such as 1950 and 1960, likely relating to the school's history timeline.

## Main Site Navigation

These links provide access to major sections of the website.

*   **School Information Links:** Links providing access to general information about the institution, including "The School" and "Institutional" details.
*   **History and Academic Sections:** Links related to specific areas of the school's history and offerings, such as "Our History," "Academics," "Arts," "Science," and "Sports."
*   **Admissions and School Levels:** Links directing users to information regarding admissions processes and specific school levels, including "Admissions," "Kinder," "Primary," and "Secondary."
*   **Community and Alumni:** Links for community engagement and former students, such as "Alumni" and "Community."

## Action and Contact Links

These links facilitate specific actions, contact requests, or access to external resources.

*   **Admissions Process:** Links related to the application process, including "Start Process," "Interview," and links specifying educational cycles like "Primary (First cycle)."
*   **Contact and Information:** Links providing contact details and documents, such as "Work with us. Send CV," "Padres - Legajos" (Parents - Records), and "Sites And Contacts."
*   **External Resources:** Links to external systems or resources, including links for "Moodle" and "Webmail."
*   **Brochure and Calendar:** Links for accessing media and scheduling, such as "Download Brochure" and "Calendar."

## Language Options

*   **Language Selection:** Links allowing users to switch the site language between English ("English"), Spanish ("Español"), and potentially other options.

## Admissions and Institutional Information

This section of the website is dedicated to providing detailed information regarding admissions, educational programs, school history, and institutional details for St. John's School. The pages are primarily structured around guiding prospective families through the application and inquiry process.

### Core Functionality

The content is organized into two main functional areas: general scheduling/information and specific application flow.

#### 1. Calendario (Admission Calendar)
This page serves as a central hub for current cycle information, educational program details, and institutional facts. It connects prospective families to various aspects of the school, including:
*   **Admissions Pathways:** Links related to general admissions, Kindergarten, Primary, and Secondary education levels.
*   **Application Process:** Links to start admission processes, request interviews, and view the school calendar.
*   **Institutional Details:** Information regarding the school's history, educational focus areas (Academic, Artistic, Scientific, etc.), community partnerships, and contact information (Sedes y Contacto).
*   **Resources:** Access points to external systems like Moodle and webmail services, as well as language options (Spanish/English).

#### 2. Entrevista (Interview Request)
This page focuses specifically on the interactive steps of the admissions process, providing parents and applicants with focused navigation related to scheduling interviews and accessing necessary documentation.
*   **Process Navigation:** Links facilitate moving through the application flow, including starting processes and viewing interview details.
*   **Stakeholder Views:** The page uses context tabs (MADRE/Mother, PADRE/Father, POSTULANTE/Applicant) to tailor information based on the user's role.
*   **Document Access:** Provides links for downloading brochures and accessing parent records (Padres - Legajos).

### Relationship Between Pages

The `calendario` page provides the broad context regarding what the school offers and when events occur, acting as a high-level informational entry point. The `entrevista` page acts as a deep dive into the actionable steps required by prospective families to initiate contact and complete their application inquiries. Together, they ensure that users can easily find both **what** the school offers and **how** to apply or inquire further.

## Section 2

_(chunk combine unavailable: Local API Error (400): {"error":"Engine protocol predict request returned 400: {\"error\":{\"code\":400,\"message\":\"request (18562 tokens) exceeds the available context size (4096 tokens), try increasing it\",\"type\":\"exceed_context_size_error\",\"n_prompt_tokens\":18562,\"n_ctx\":4096}}"})_

## Digital Blueprint: Alumni and Institutional Information Hub

This section of the website is dedicated to providing alumni engagement, historical information, institutional details, and application resources for prospective students. The pages work together to guide former and current students through the school's history, educational offerings, and pathways for involvement.

### Overview

The linked pages establish a comprehensive portal that connects alumni with the institution's history, academic focus areas, partnership agreements, and practical actions such as admissions and contact information. The content is structured around core educational components (Kindergarten, Primary, Secondary, Academics) while providing specific resources tailored for alumni.

### Page Details

#### 1. Alumni Stories & Communication
**Route:** `/Web/alumni/have-you-heard`
**Description:** This page serves as an engagement point for alumni by sharing the "stories of our former students" and promoting updates via a newsletter subscription.
**Functionality:** It provides access to general school information (Admissions, History, Academics) and specific educational focus areas (Arts, Science, Sports, Social Skills). It also features links for alumni actions (Start Process, Interview) and links to specific alumni profiles.

#### 2. Alumni Trivia & Action Items
**Route:** `/Web/alumni/sabias-que`
**Description:** This page functions as a resource hub for alumni, offering interesting facts alongside practical resources for interacting with the school.
**Functionality:** It connects the general institutional information (Admissions, School History, Contact) with specific alumni actions (Download Brochure, Interview, Calendar). It also includes links to view specific alumni profiles and provides language options (English/Español).

#### 3. Institutional Agreements & Partnerships
**Route:** `/Web/el-colegio/convenios`
**Description:** This page details the school's agreements and partnerships with other educational institutions, emphasizing a commitment to maintaining high international standards.
**Functionality:** It provides navigation links across all main institutional sections (Admissions, History, Educational Focus Areas) and links to utility systems (Moodle, Webmail). Crucially, it features custom selectable options for specific diploma/alliance programs (e.g., IB Diploma, Universidad Austral), linking the school's educational offerings directly to external academic bodies.

### System Integration Summary

The three pages are tightly integrated:
*   **Institutional Context:** The `/el-colegio/convenios` page provides the foundational context regarding institutional partnerships and structure.
*   **Alumni Focus:** The alumni-specific routes (`have-you-heard` and `sabias-que`) leverage this context to provide specific resources, historical facts, contact methods, and actionable steps for alumni.
*   **Action Flow:** Both alumni pages offer direct calls to action (e.g., Start Process, Interview) that link back into the broader application and scheduling framework established by the institutional structure.

_(section summary unavailable: Response truncated: the model hit max_tokens before finishing (finish_reason: 'length'). This is almost always max_tokens set too low for a reasoning model's chain-of-thought - raise agents.local.max_tokens (or LOCAL_MAX_TOKENS) in pragma.yaml/.env and try again, or unset it entirely to let the model use as much as it needs.)_

- stjohns.edu.ar/Web/files/Site/brochure_institucional_2023_b.pdf [Pending, 0 components]
- stjohns.edu.ar/Web/home [Scouted, 59 components]
  Description: Desarrollamos la confianza, la independencia y la autoestima de los niños a través del juego, su mayor fuente de aprendizaje.
  Components:
## Navigation and Utility

*   **Previous:** Navigates to the previous page.
*   **Next:** Navigates to the next page.
*   **Toggle navigation:** Controls the visibility of the main navigation menu.

## Admissions and School Information

This section contains links related to admissions, educational levels, and contact information:

*   **Admisiones (x4):** Links related to admissions processes.
*   **Kinder:** Links related to Kindergarten information.
*   **Primaria:** Links related to Primary education.
*   **Secundaria:** Links related to Secondary education.
*   **Kindergarten:** Link for Kindergarten information.
*   **Educación Primaria:** Link for Primary Education details.
*   **Educación Secundaria:** Link for Secondary Education details.
*   **Admisión:** Link to the admission process.
*   **Iniciar proceso:** Link to start an application or process.
*   **Entrevista:** Link related to interviews.
*   **Calendario:** Link to view the school calendar.
*   **Descargar Folleto:** Link to download a brochure.
*   **Sedes y Contacto (x2):** Links providing information about locations and contact details.

## Institutional Information

*   **St. John's School:** Link to the main school page.
*   **El Colegio:** Link providing general school information.
*   **Institucional:** Link to institutional information.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Convenios:** Link for agreements or partnerships.

## Academic and Curriculum Areas

These links cover the various areas of the school's educational focus:

*   **Formación Integral:** Information regarding integral education.
*   **Académica:** Information related to academic matters.
*   **Artística:** Information related to artistic studies.
*   **Científica:** Information related to scientific studies.
*   **Deportiva:** Information related to sports and physical education.
*   **Humana:** Information related to humanities.
*   **Proyecto Educativo:** Details about the educational project.
*   **Propuesta Educativa:** Details about the educational proposal.
*   **Kindergarten:** Link for Kindergarten programs.

## Community and Alumni

*   **Alumni:** Information for former students.
*   **Comunidad:** Information about the school community.
*   **¿Sabías qué? (x2):** Links to interesting facts or trivia.

## Language Options

*   **Español:** Link for the Spanish language version.
*   **English:** Link for the English language version.

## External and System Links

*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to the school webmail service.
*   **ES:** Link related to Spanish.
*   **Padres - Legajos:** Link likely related to parents' records or files.
*   **Webmail:** Link to the webmail service (repeated).

## Other Links

*   **Ver más (x3):** Links used to expand content.
*   **(no accessible label found on this element) (x4):** Unlabeled links present on the page.
- stjohns.edu.ar/Web/home?lang=EN [Scouted, 61 components]
  Description: ENVIRONMENTAL AWARENESS
  Components:
## Navigation

This section contains links used for navigating between pages or sections of the website.

*   **Previous**: Navigates to the previous page.
*   **Next**: Navigates to the next page.
*   **Toggle navigation**: Controls the visibility of the main navigation menu.

## School Identity and Information

These links provide general information about the institution, history, and contact details.

*   **St. John's School**: Links to the main school homepage.
*   **The School**: Provides information about the school itself.
*   **Institutional**: Details related to the school's institutional structure or policies.
*   **Our History**: Displays the history of the school.
*   **Agreements**: Information regarding agreements related to the school.
*   **Sites And Contacts**: Links to general site information and contact details.

## Admissions and Application Process

These links guide users through the process of applying to the school.

*   **Admissions**: General admissions information.
*   **Kinder**: Information specific to Kindergarten admissions.
*   **Primary**: Information specific to Primary school admissions.
*   **Secondary**: Information specific to Secondary school admissions.
*   **Admission**: Link related to the admission process.
*   **Start Process**: Initiates the application or enrollment process.
*   **Interview**: Information or access related to the interview stage.
*   **Calendar**: Accesses the school calendar.
*   **Download Brochure**: Allows users to download a brochure.

## Academic and Program Details

This group covers links detailing the educational offerings, curriculum, and student groups.

*   **Kindergarten**: Information regarding Kindergarten programs.
*   **Primary School**: Information regarding Primary School programs.
*   **Secondary School**: Information regarding Secondary School programs.
*   **Alumni**: Information for former students.
*   **Community**: Information related to the school's community involvement.
*   **Academics**: Details about the academic structure and offerings.
*   **Arts**: Information related to the Arts curriculum.
*   **Science**: Information related to the Science curriculum.
*   **Sports**: Information related to sports programs.
*   **Social Skills**: Information related to social skills development.
*   **Educational Project**: Details about educational projects offered.
*   **Educational Proposal**: Access to educational proposals.

## School Systems and Resources

Links directing users to internal school systems or specific resources.

*   **Moodle**: Link to the Moodle learning management system.
*   **Webmail**: Access to the school's webmail service.
*   **Administration**: Information related to school administration.

## Language Options

These links allow users to switch the language of the page.

*   **EN**: Selects the English language.
*   **Español**: Selects the Spanish language.
*   **English**: Selects the English language (alternate link).

## Additional Links

*   **Have you heard**: A link prompting users to view related content or announcements.
*   **View More**: Link used to expand a list of options.
*   **(no accessible label found on this element)**: Placeholder links that are present but lack visible labels.
- stjohns.edu.ar/Web/home?lang=SP [Scouted, 59 components]
  Description: Desarrollamos la confianza, la independencia y la autoestima de los niños a través del juego, su mayor fuente de aprendizaje.
  Components:
## Navigation and Page Controls

*   **Previous:** Link to navigate to the previous page.
*   **Next:** Link to navigate to the next page.
*   **Toggle navigation:** Button to show or hide the main navigation menu.

## Main Menu Links (School Information)

This section contains links related to the school's structure, history, and contact information:

*   **El Colegio:** Link providing information about the school.
*   **Institucional:** Link for institutional information.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Convenios:** Link for agreements or partnerships.
*   **Sedes y Contacto:** Link for locations and contact details.
*   **¿Sabías qué?:** Link to interesting facts.

## Educational Programs and Levels

This group covers links related to educational levels and academic focus areas:

*   **Admisiones (Multiple instances):** Links related to admissions procedures.
*   **Kinder:** Link related to Kindergarten.
*   **Primaria:** Link related to Primary education.
*   **Secundaria:** Link related to Secondary education.
*   **Primaria (Primer ciclo):** Link specifically for the first cycle of Primary education.
*   **Formación Integral:** Link regarding integral education.
*   **Académica:** Link for academic information.
*   **Artística:** Link for artistic subjects.
*   **Científica:** Link for scientific subjects.
*   **Deportiva:** Link for sports/physical education.
*   **Humana:** Link for humanities subjects.
*   **Proyecto Educativo:** Link concerning the educational project.
*   **Propuesta Educativa:** Link regarding the educational proposal.

## Student and Alumni Resources

*   **Padres - Legajos:** Link to access parent records.
*   **Alumni:** Link for alumni information.
*   **Comunidad:** Link related to the school community.

## Application and Process Links

This section contains links guiding users through the admissions process:

*   **Admisión (Multiple instances):** Links related to the admission process.
*   **Iniciar proceso:** Link to start an application process.
*   **Entrevista:** Link for scheduling or viewing interview details.
*   **Calendario:** Link to view the school calendar.
*   **Descargar Folleto:** Link to download a brochure.

## External and System Links

*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to webmail services.
*   **St. John's School:** Link to the school's main page or branding.
*   **Webmail:** Link related to email services.

## Language Selection

*   **ES:** Link for the Spanish language version.
*   **Español:** Link for the Spanish language version.
*   **English:** Link for the English language version.

## Additional Information Links

*   **¿Sabías qué?:** Another link to interesting facts.
*   **Ver más (Multiple instances):** Links used to expand or view more content.
*   **(no accessible label found on this element) (Multiple instances):** Unlabeled links present on the page.
- stjohns.edu.ar/Web/proyecto-educativo/kindergarten [Scouted, 54 components]
  Description: KINDER - Desde sala de uno a sala de cinco, las actividades del Kinder están basadas en el juego que es la principal fuente de aprendizaje de los niños. Con variadas actividades y propuestas para que ellos desarrollen su capacidad intelectual, física, emocional, lingüística y social en un ambiente e
  Components:
### Navigation and School Information

This section includes links for navigating the main sections of the website, providing institutional details, and accessing contact information.

*   **Navigation Links:** Links labeled "Admisiones" (Admissions), "Kinder" (Kindergarten), "Primaria" (Primary), and "Secundaria" (Secondary) appear multiple times, likely acting as primary navigation points for different levels or processes.
*   **Institutional Details:** Links provide information about the school, including "El Colegio" (The School), "Institucional" (Institutional), "Nuestra Historia" (Our History), "Convenios" (Agreements), and "Sedes y Contacto" (Locations and Contact).
*   **Programmatic Focus:** Links detail the educational focus, such as "Formación Integral" (Integral Education), "Académica" (Academic), "Artística" (Artistic), "Científica" (Scientific), "Deportiva" (Sports), and "Humana" (Humanities).
*   **Curriculum Links:** Specific links reference educational levels, including "Kindergarten," "Educación Primaria" (Primary Education), and "Educación Secundaria" (Secondary Education).
*   **Alumni & Community:** Links are provided for "Alumni" and "Comunidad" (Community).

### Admissions and Application Process

These components relate to the process of enrolling or inquiring about admission.

*   **Admission Procedures:** Links related to admissions include "Admisiones" and a general "Admisión."
*   **Process Steps:** Links guide users through the application steps, such as "Iniciar proceso" (Start process), "Entrevista" (Interview), and "Calendario" (Calendar).
*   **Document Access:** Links allow users to access materials like "Descargar Folleto" (Download Brochure) and "Padres - Legajos" (Parents - Records).

### External and Utility Links

These components link to external resources or utility features.

*   **External Resources:** Links lead to external platforms such as "Moodle" and "Webmail."
*   **School Identity:** A link references the school name: "St. John's School."
*   **FAQ:** Links are provided for frequently asked questions, labeled "¿Sabías qué?" (Did you know?).

### Language Options

Links allow users to view content in different languages:

*   Español (Spanish)
*   English

### Custom Controls and Data Fields

These components handle specific data presentation or interaction.

*   **Team/Staff:** Two custom controls display the text "Equipo de profesionales" (Team of professionals).
*   **Hidden Fields:** Several text fields are present but do not display accessible labels.

_(section summary unavailable: Response truncated: the model hit max_tokens before finishing (finish_reason: 'length'). This is almost always max_tokens set too low for a reasoning model's chain-of-thought - raise agents.local.max_tokens (or LOCAL_MAX_TOKENS) in pragma.yaml/.env and try again, or unset it entirely to let the model use as much as it needs.)_

- stjohns.edu.ar/Web/proyecto-educativo/primaria [Scouted, 54 components]
  Description: PRIMARIA - El enfoque con respecto al aprendizaje de las dos lenguas es comunicacional, privilegiando el contacto con diferentes tipos de textos y favoreciendo la posibilidad de expresarse correctamente en diferentes situaciones y por distintos medios. Con visitas semanales a la biblioteca nuestros 
  Components:
### Navigation and Admissions Links

This section contains links primarily focused on admissions, educational levels, and application processes.

*   **Admisiones:** Links related to admission procedures or information.
*   **Kinder:** Link related to Kindergarten programs.
*   **Primaria:** Link related to Primary education.
*   **Secundaria:** Link related to Secondary education.
*   **Primaria (Primer ciclo):** Specific link for the Primary cycle.
*   **Admisión:** General link to start the admission process.
*   **Iniciar proceso:** Link to begin an application or process.
*   **Entrevista:** Link related to scheduling or accessing interview information.
*   **Calendario:** Link to view a schedule or calendar.
*   **Descargar Folleto:** Link to download a brochure.

### Institutional and Informational Links

These links provide details about the school, its history, academic focus, and contact information.

*   **El Colegio:** Link providing information about the institution.
*   **Institucional:** Link to institutional information.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Convenios:** Link related to agreements or partnerships.
*   **Sedes y Contacto:** Link providing location details and contact information.
*   **¿Sabías qué?:** Links offering general facts or trivia.
*   **Formación Integral:** Link detailing the comprehensive education offered.
*   **Académica:** Link related to academic matters.
*   **Artística:** Link related to artistic programs.
*   **Científica:** Link related to scientific programs.
*   **Deportiva:** Link related to sports or physical education.
*   **Humana:** Link related to humanistic studies.
*   **Proyecto Educativo:** Link detailing the educational project.
*   **Propuesta Educativa:** Link detailing the educational proposal.
*   **Comunidad:** Link related to the school community.
*   **Alumni:** Link for former students or alumni information.
*   **Convenios y Alianzas:** Link specifically for agreements and alliances.

### Program and Subject Links

Links related to specific educational stages and subject areas.

*   **Kindergarten:** Link related to Kindergarten.
*   **Educación Primaria:** Link related to Primary Education.
*   **Educación Secundaria:** Link related to Secondary Education.
*   **Español:** Link for the Spanish language program.
*   **English:** Link for the English language program.

### System and External Links

Links directing users to external platforms or internal systems.

*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to webmail services.
*   **St. John's School:** Link likely pointing to the school homepage.
*   **El Colegio:** Link (repeated, context dependent).

### Team Information

Components displaying information about the professional team.

*   **Equipo de profesionales:** Custom control displaying the team of professionals.
- stjohns.edu.ar/Web/proyecto-educativo/secundaria [Scouted, 54 components]
  Description: SECUNDARIA - Los alumnos que cursan el secundario de 1° a 6° año profundizan los conocimientos adquiridos en la etapa anterior con el fin de lograr la excelencia académica. El objetivo es que combinen el trabajo autónomo con la capacidad analítica, y se formen como individuos íntegros a partir de va
  Components:
## Navigation and Admissions

This section contains links related to school admissions, grade levels, and application processes.

*   **Admisiones:** Links for general admissions information or application steps.
*   **Kinder:** Link related to kindergarten programs.
*   **Primaria:** Link related to primary education.
*   **Secundaria:** Link related to secondary education.
*   **Primaria (Primer ciclo):** Link specifically for the primary cycle.
*   **Admisión:** Link to start the admission process.
*   **Iniciar proceso:** Link to begin a specific process.
*   **Entrevista:** Link related to scheduling or information about interviews.
*   **Calendario:** Link to view the school calendar.
*   **Descargar Folleto:** Link to download a brochure.

## Institutional Information

This section provides details about the school, history, and contact information.

*   **El Colegio:** Link providing general institutional information.
*   **Institucional:** Link for institutional details.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Convenios:** Link related to agreements and partnerships.
*   **Sedes y Contacto:** Link providing locations and contact details.
*   **¿Sabías qué?:** Links providing interesting facts or trivia.
*   **Webmail:** Link to access webmail services.
*   **St. John's School:** Link identifying the school.

## Educational Focus Areas

These links categorize the educational focus areas offered by the school.

*   **Formación Integral:** Link related to integral education.
*   **Académica:** Link focused on academic subjects.
*   **Artística:** Link focused on artistic subjects.
*   **Científica:** Link focused on scientific subjects.
*   **Deportiva:** Link focused on sports and physical education.
*   **Humana:** Link focused on humanities.
*   **Proyecto Educativo:** Link related to the educational project.
*   **Propuesta Educativa:** Link related to the educational proposal.

## Alumni and Community

Links dedicated to former students and community engagement.

*   **Alumni:** Link for alumni information.
*   **Comunidad:** Link related to the school community.

## Resources and Media Links

Links leading to external resources or specific documents.

*   **Moodle:** Link to Moodle platform content.
*   **Webmail:** Link to webmail services.
*   **Padres - Legajos:** Link for parents accessing records.

## Language Options

Links allowing users to switch the language of the page.

*   **ES:** Link for Spanish.
*   **Español:** Link for Spanish.
*   **English:** Link for English.

## Team and Custom Controls

Information displayed regarding the professional team and custom interactive elements.

*   **Equipo de profesionales:** Displays information about the professional team (appears twice).
- stjohns.edu.ar/Web/the-school/agreements [Scouted, 63 components]
  Description: AGREEMENTS AND JOINT VENTURES - We have established ties with the main English speaking educational institutions and share sports and cultural activities with them. Our academic standards are in accordance with the highest world standards. Agreements signed with prestigious, private Argentine univer
  Components:
## Navigation and School Information

This section contains links for navigating different sections of the school website, focusing on admissions, academic levels, history, and contact information.

*   **Admissions:** Links related to application processes, including general admissions, kindergarten admissions, primary admissions, secondary admissions, and specific admission cycles (e.g., Primary (First cycle)).
*   **School Levels:** Links for viewing information about Kindergarten, Primary School, and Secondary School.
*   **Academics & Programs:** Links providing details on various educational areas such as Integral Formation, Academics, Arts, Science, Sports, and Social Skills.
*   **History & Administration:** Links providing institutional information, including Our History, Administration, and Agreements.
*   **Contact & Resources:** Links for accessing external resources and contact details, such as Sites And Contacts, Have you heard, Educational Proposal, and Download Brochure.

## Application and Process Links

These links guide users through specific steps related to enrollment or inquiry.

*   **Process Initiation:** Links to start processes, including Start Process and Interview.
*   **Contact & Resources:** Links providing contact information and external resources, such as Work with us. Send CV, Padres - Legajos, Moodle, and Webmail.
*   **General Navigation:** Links for general navigation like Admissions, Kinder, Primary, Secondary, and Alumni.

## Language Selection

Links allowing users to switch the language of the page content.

*   **Language Options:** Links for English (English), Spanish (Español), and English (EN).

## Custom Selections/Branding

These components appear to be custom selectors or branding elements, likely related to diploma or university affiliations.

*   **Diploma/Affiliation Selections:** Components allowing selection of specific educational credentials or institutions: IB DIPLOMA (listed twice), ALLIANCE FRANÇAISE (listed twice), SAINT ANDREWS´S UNIVERSITY (listed twice), and TORCUATO DI TELLA UNIVERSITY.
- stjohns.edu.ar/Web/{token}/Academica [Scouted, 59 components]
  Description: FORMACIÓN INTEGRAL - St. John’s siempre se ha caracterizado por ofrecer una sólida formación académica. Alentamos a nuestros alumnos a desarrollar todo el potencial que llevan dentro y a seguir aspirando a superarse día a día. Trabajamos día a día de forma integrada inculcando valores a nuestros alu
  Components:
## Navigation and Admissions Links

This section contains links related to admissions, grade levels, and academic information.

*   **Admisiones:** Links related to admissions processes or information.
*   **Kinder:** Links related to Kindergarten information.
*   **Primaria:** Links related to Primary education.
*   **Secundaria:** Links related to Secondary education.
*   **Admisiones (Repeat):** Additional links regarding admissions.
*   **Kinder (Repeat):** Additional links regarding Kindergarten.
*   **Primaria (Primer ciclo):** Link specific to the first cycle of Primary education.
*   **Padres - Legajos:** Link related to parent records/files.

## Academic and Program Links

This section includes links detailing the school's educational offerings, focus areas, and academic departments.

*   **Académica:** Link to academic information.
*   **Artística:** Link to artistic programs or information.
*   **Científica:** Link to scientific programs or information.
*   **Deportiva:** Link to sports or athletic programs or information.
*   **Humana:** Link to humanities programs or information.
*   **Proyecto Educativo:** Link to the educational project.
*   **Propuesta Educativa:** Link to the educational proposal.

## School Information and History

Links providing general institutional details, history, and contact information.

*   **El Colegio:** Link related to the school itself.
*   **Institucional:** Link to institutional information.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Convenios:** Link regarding agreements or partnerships.
*   **Sedes y Contacto:** Link providing locations and contact details (appears multiple times).
*   **¿Sabías qué?:** Links containing interesting facts.

## Alumni and Community

Links focusing on former students and the school community.

*   **Alumni:** Link for alumni information.
*   **Comunidad:** Link related to the school community.

## Academic Levels and Language

Links specifying academic levels and language options.

*   **Kindergarten:** Link for Kindergarten.
*   **Educación Primaria:** Link for Primary education.
*   **Educación Secundaria:** Link for Secondary education.
*   **Español:** Link for Spanish language options.
*   **English:** Link for English language options.

## Administrative and Process Links

Links related to specific processes, documents, and external resources.

*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to webmail access.
*   **Iniciar proceso:** Link to start a process (likely an application).
*   **Entrevista:** Link for scheduling or viewing interview information.
*   **Calendario:** Link to the school calendar.
*   **Descargar Folleto:** Link to download a brochure.

## Specific Links and Expansion

Miscellaneous links found on the page.

*   **St. John's School:** Link referring to the school name.
*   **(no accessible label found on this element) (x6):** Several links with no visible text label, likely placeholders or navigation elements.
*   **Ver más:** Links used to expand content or view more information.
- stjohns.edu.ar/Web/{token}/Academics [Scouted, 61 components]
  Description: INTEGRAL FORMATION - St. John´s has always offered solid academic preparation to its students, fostering the strengthening of their individual potential and encouraging them to embrace life-long learning. Our integrated programme includes pastoral care based on values designed to develop our student
  Components:
## Academics Navigation

This section contains links for navigating different academic areas and program levels.

*   **Admissions**: Link to admissions information.
*   **Kinder**: Link related to Kindergarten information.
*   **Primary**: Link related to Primary level information.
*   **Secondary**: Link related to Secondary level information.
*   **Admissions**: Another link related to admissions.
*   **Kinder**: Another link related to Kindergarten information.
*   **Primary (First cycle)**: Link specific to the Primary School First cycle.
*   **Administration**: Link to administration details.
*   **Academics**: Link to general academics information.
*   **Arts**: Link to Arts information.
*   **Science**: Link to Science information.
*   **Sports**: Link to Sports information.
*   **Social Skills**: Link to Social Skills information.
*   **Educational Project**: Link related to Educational Projects.
*   **Educational Proposal**: Link related to Educational Proposals.
*   **Kindergarten**: Link related to Kindergarten.
*   **Primary School**: Link related to Primary School.
*   **Secondary School**: Link related to Secondary School.

## Institutional Information & Links

This section contains links providing details about the school, history, and contact information.

*   **The School**: Link providing information about the school.
*   **Institutional**: Link related to institutional details.
*   **Our History**: Link detailing the school's history.
*   **Agreements**: Link to agreements.
*   **Sites And Contacts**: Link to sites and contacts.
*   **Have you heard**: Link with the text "Have you heard".

## Application & Process Links

These links guide users through application or inquiry processes.

*   **Work with us. Send CV**: Link for sending a CV or working with the institution.
*   **Padres - Legajos**: Link related to parents and records (Legajos).
*   **Moodle**: Link to Moodle platform.
*   **Webmail**: Link to Webmail access.
*   **Start Process**: Link to start an application process.
*   **Interview**: Link related to interviews.
*   **Calendar**: Link to the school calendar.
*   **Download Brochure**: Link to download a brochure.

## Alumni & External Links

Links directed toward specific groups or external resources.

*   **Alumni**: Link for alumni information.
*   **Community**: Link related to the community.

## Language Selection

Links allowing selection of different languages:

*   **EN**: English language option.
*   **Español**: Spanish language option.
*   **English**: English language option.

## Miscellaneous Navigation Links

These are general navigation or informational links.

*   **(no accessible label found on this element)** (x3): Unlabeled link elements.
*   **View More**: Link to view more content.
*   **(no accessible label found on this element)** (x4): Unlabeled link elements.

_(section summary unavailable: Response truncated: the model hit max_tokens before finishing (finish_reason: 'length'). This is almost always max_tokens set too low for a reasoning model's chain-of-thought - raise agents.local.max_tokens (or LOCAL_MAX_TOKENS) in pragma.yaml/.env and try again, or unset it entirely to let the model use as much as it needs.)_

- stjohns.edu.ar/Web/{token}/Artistica [Scouted, 57 components]
  Description: FORMACIÓN ARTÍSTICA - St. John's ofrece una experiencia viva y dinámica que complementa la cultura general de los alumnos. Estudiar en St. John's es tener acceso a las mejores herramientas para desarrollar tu potencial y superarte día a día.
  Components:
## Navigation and School Information

This section groups links related to general school information, institutional details, and contact methods.

### School Identity and Institutional Links
*   **St. John's School:** Link leading to information about St. John's School.
*   **El Colegio:** Link providing information about the school itself.
*   **Institucional:** Link to institutional information.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Convenios:** Link related to agreements or partnerships.
*   **Sedes y Contacto:** Link providing location and contact details.

### Academic Areas and Programs
*   **Artística:** Link related to Artistic studies.
*   **Científica:** Link related to Scientific studies.
*   **Deportiva:** Link related to Sports studies.
*   **Humana:** Link related to Human studies.
*   **Proyecto Educativo:** Link concerning the Educational Project.
*   **Propuesta Educativa:** Link concerning the Educational Proposal.

### Educational Levels and Admissions
This section groups links related to different educational stages, admissions processes, and required documentation.

*   **Admisiones:** Links related to admission procedures (appears multiple times).
*   **Kinder:** Links related to Kindergarten admissions or information.
*   **Primaria (Primer ciclo):** Link related to Primary education (First cycle).
*   **Educación Primaria:** Link related to Primary Education.
*   **Educación Secundaria:** Link related to Secondary Education.
*   **Kindergarten:** Link related to Kindergarten.
*   **Alumni:** Link for alumni information.

### Process and Inquiry Links
*   **¿Sabías qué?:** Links offering interesting facts or trivia.
*   **Formación Integral:** Link about integral education.
*   **Académica:** Link related to academic matters.
*   **Padres - Legajos:** Link likely for parents accessing records/files.
*   **Entrevista:** Link to initiate an interview process.
*   **Calendario:** Link to view the school calendar.
*   **Descargar Folleto:** Link to download a brochure or leaflet.

### External and Utility Links
*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to webmail services.
*   **Español:** Language selection link for Spanish.
*   **English:** Language selection link for English.

## Hidden Fields

The following elements are hidden text fields without accessible labels:
*   Two hidden text fields, likely used for internal data tracking or form input.
- stjohns.edu.ar/Web/{token}/Arts [Scouted, 57 components]
  Description: ARTS - St. John´s offers true and dynamic experiences to enhance students´ general knowledge. Studying at St. John´s provides the best tools to develop their potential and to improve constantly.
  Components:
## Navigation and School Structure

This section groups links related to navigation, institutional details, and school levels.

### Admissions and School Levels
*   **Admissions:** Links related to the admissions process, including general admissions information, starting the application process, and interview scheduling.
*   **Kindergarten:** Links providing information specific to Kindergarten programs.
*   **Primary School:** Links detailing information about Primary School education.
*   **Secondary School:** Links providing information about Secondary School education.
*   **Admission:** General links related to admissions.
*   **Primary (First cycle):** Specific information regarding the first cycle of Primary education.

### Institutional Information
*   **The School:** Link leading to general information about the school.
*   **Institutional:** Links providing details about the institution.
*   **Our History:** Information regarding the school's history.
*   **Agreements:** Documents or information related to agreements.
*   **Sites And Contacts:** Links for finding other sites and contact information.

### Curriculum and Programs
*   **Academics:** Links providing academic details.
*   **Arts:** Information concerning Arts programs.
*   **Science:** Information concerning Science programs.
*   **Sports:** Information concerning Sports programs.
*   **Social Skills:** Information concerning Social Skills development.
*   **Educational Project:** Details about educational projects.
*   **Educational Proposal:** Information regarding educational proposals.

### Community and Alumni
*   **Alumni:** Resources or information for alumni.
*   **Community:** Information related to the school community.

## School Links and Utilities

This section covers links related to specific administrative functions, systems, and media.

### Administrative and Contact Links
*   **Administration:** Links related to school administration.
*   **Work with us. Send CV:** A link for job applications or sending a curriculum vitae.
*   **Padres - Legajos:** Links related to parent records or files.
*   **Webmail:** Access or information regarding the webmail system.
*   **Moodle:** Link to the Moodle learning management system.

### Media and Calendar
*   **Download Brochure:** A link to download a school brochure.
*   **Calendar:** Access to the school calendar.

## Language Options

Links providing content in different languages:
*   **EN:** English language option.
*   **Español:** Spanish language option.
*   **English:** English language option (redundant with EN, likely an alternative link).

***

*Note: Several components were identified as hidden text fields or links without accessible labels and are not described above.*
- stjohns.edu.ar/Web/{token}/Cientifica [Scouted, 51 components]
  Description: FORMACIÓN CIENTÍFICA - St. John's estimula a los alumnos a descubrir y desarrollar su potencial al más alto nivel en un ambiente apto para una educación intensiva e integral.
  Components:
### Navigation and School Information

This section contains links for navigating different sections of the website, including institutional information and general school details.

*   **Admisiones:** Links related to admissions processes.
*   **Kinder:** Links related to Kindergarten admission or information.
*   **Primaria (Primer ciclo):** Links related to Primary education.
*   **Secundaria:** Links related to Secondary education.
*   **Padres - Legajos:** Link for parents' records.
*   **Moodle:** Link to Moodle platform.
*   **Webmail:** Link to webmail access.
*   **St. John's School:** Link to the main school page.
*   **El Colegio, Institucional, Nuestra Historia, Convenios, Sedes y Contacto:** Links providing institutional and contact details.
*   **¿Sabías qué?:** Links for general information or FAQs.
*   **Formación Integral, Académica, Artística, Deportiva, Humana, Proyecto Educativo, Propuesta Educativa:** Links detailing the educational focus areas.
*   **Kindergarten, Educación Primaria, Educación Secundaria:** Specific links related to educational levels.
*   **Alumni, Comunidad:** Links for alumni and community information.

### Action and Process Links

This group includes links that initiate specific processes or provide access to external resources.

*   **Admisión:** Link to start the admission process.
*   **Iniciar proceso:** Link to begin a specific process.
*   **Entrevista:** Link related to interviews.
*   **Calendario:** Link to view the calendar.
*   **Descargar Folleto:** Link to download a brochure.

### Language and External Links

*   **ES, Español, English:** Links to switch between Spanish and English language versions of the content.

### Hidden Fields

The page contains several text fields that are not visible to the user.
- stjohns.edu.ar/Web/{token}/Humana [Scouted, 51 components]
  Description: FORMACIÓN HUMANA - Estudiar en St. John's es formar parte de una comunidad donde promovemos la conciencia social e impulsamos a nuestros alumnos a asumir un compromiso con el mundo en que viven desde el lugar que ocupan.
  Components:
## Navigation and Admissions Links

This section contains various links related to admissions, educational levels, and administrative procedures.

### Admissions and Grade Levels
*   **Admisiones:** Link for admissions information.
*   **Kinder:** Link related to Kindergarten admission or information.
*   **Primaria:** Link related to Primary education.
*   **Secundaria:** Link related to Secondary education.
*   **Admisiones (Repeated):** Another link for admissions.
*   **Kinder (Repeated):** Another link for Kindergarten.
*   **Primaria (Primer ciclo):** Link specifically for Primary (First cycle).

### Administrative and Academic Links
*   **Padres - Legajos:** Link to access parent records or files.
*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to the webmail service.
*   **St. John's School:** Link referencing the school name.

### Educational Programs and Information
*   **Kindergarten:** Link for Kindergarten information.
*   **Educación Primaria:** Link for Primary education information.
*   **Educación Secundaria:** Link for Secondary education information.
*   **Alumni:** Link for alumni information.
*   **Humana:** Link related to the Human stream or program.

### Institutional and Contact Information
*   **El Colegio:** Link providing institutional details.
*   **Institucional:** Link to institutional information.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Convenios:** Link for agreements or partnerships.
*   **Sedes y Contacto (Repeated):** Links related to school locations and contact information.
*   **¿Sabías qué?:** General informational links (appears multiple times).
*   **Formación Integral:** Link regarding integral education.
*   **Académica:** Link for academic information.
*   **Artística:** Link for artistic programs or information.
*   **Científica:** Link for scientific programs or information.
*   **Deportiva:** Link for sports or physical education.
*   **Comunidad:** Link related to the school community.

### Application Process Links
*   **Admisión:** Link to start the admission process.
*   **Iniciar proceso:** Link to begin the application process.
*   **Entrevista:** Link related to interviews.
*   **Calendario:** Link to view the calendar.
*   **Descargar Folleto:** Link to download a brochure.

### Language and School Type Links
*   **ES:** Link referring to Spanish (likely as a language option).
*   **Español:** Link for the Spanish language version.
*   **English:** Link for the English language version.

### Miscellaneous Links
*   **Webmail:** Link to access webmail.
*   **Proyecto Educativo:** Link for the educational project.
*   **Propuesta Educativa:** Link for the educational proposal.
- stjohns.edu.ar/Web/{token}/Kindergarten [Scouted, 54 components]
  Description: KINDER - Desde sala de uno a sala de cinco, las actividades del Kinder están basadas en el juego que es la principal fuente de aprendizaje de los niños. Con variadas actividades y propuestas para que ellos desarrollen su capacidad intelectual, física, emocional, lingüística y social en un ambiente e
  Components:
## Navigation and Admissions Links

This section contains various navigation links related to admissions, educational levels, and school information.

*   **Admisiones:** Link for admissions information.
*   **Kinder:** Link related to Kindergarten.
*   **Primaria:** Link related to Primary education.
*   **Secundaria:** Link related to Secondary education.
*   **Admisiones (Repeated):** Another link for admissions.
*   **Kinder (Repeated):** Another link for Kindergarten.
*   **Primaria (Primer ciclo):** Link specifically for the Primary (First cycle).
*   **Padres - Legajos:** Link related to parent records/files.
*   **Admisión:** Link to start the admission process.
*   **Iniciar proceso:** Link to initiate a specific process.
*   **Entrevista:** Link related to scheduling an interview.
*   **Calendario:** Link to view the calendar.
*   **Descargar Folleto:** Link to download a brochure/leaflet.
*   **Sedes y Contacto (Repeated):** Links for locations and contact information.
*   **ES:** Link labeled "ES".
*   **Español:** Link for Spanish language options.
*   **English:** Link for English language options.
*   **Convenios y Alianzas:** Link for agreements and alliances.

## Institutional Information

This section includes links providing details about the school, its history, and educational focus.

*   **St. John's School:** Link referring to the school name.
*   **El Colegio:** Link for information about the school.
*   **Institucional:** Link for institutional information.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Formación Integral:** Link related to integral education.
*   **Académica:** Link related to academic matters.
*   **Artística:** Link related to artistic subjects.
*   **Científica:** Link related to scientific subjects.
*   **Deportiva:** Link related to sports/physical education.
*   **Humana:** Link related to humanistic studies.
*   **Proyecto Educativo:** Link for the educational project.
*   **Propuesta Educativa:** Link for the educational proposal.
*   **Kindergarten:** Link specifically for Kindergarten information.
*   **Educación Primaria:** Link for Primary Education.
*   **Educación Secundaria:** Link for Secondary Education.
*   **Alumni:** Link for alumni information.
*   **Comunidad:** Link related to the school community.
*   **¿Sabías qué?:** Links providing interesting facts.

## External and System Links

Links leading to external systems or communication tools.

*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to webmail services.
*   **(no accessible label found on this element) (x2):** Two unlabelled links.

## Team/Staff Information

This section displays information about the professional team.

*   **Equipo de profesionales (x2):** Links related to the team of professionals.

_(section summary unavailable: Response truncated: the model hit max_tokens before finishing (finish_reason: 'length'). This is almost always max_tokens set too low for a reasoning model's chain-of-thought - raise agents.local.max_tokens (or LOCAL_MAX_TOKENS) in pragma.yaml/.env and try again, or unset it entirely to let the model use as much as it needs.)_

- stjohns.edu.ar/Web/{token}/Kindergarteneng [Scouted, 56 components]
  Description: KINDER - From two year olds through five year olds, activities in the kInderegarten are based on play, the main tool in the learning process of small chilren. Activities in our integrated curriculum are designed to stimulate the development of social, emotional, linguistic, intellectual and physical
  Components:
## Navigation and Institutional Links

This section includes links for navigating the school's structure, history, and contact information.

*   **Toggle navigation:** A button used to show or hide the main navigation menu.
*   **The School:** Link leading to general information about the school.
*   **Institutional:** Link providing institutional details.
*   **Our History:** Link detailing the school's history.
*   **Agreements (x3):** Links related to various agreements or policies.
*   **Sites And Contacts (x2):** Links for accessing sites and contact information.
*   **Community:** Link related to the school community.

## Admissions and School Levels

These links direct users to information regarding admissions and specific educational cycles.

*   **Admissions:** General link for admissions information.
*   **Kinder:** Link related to Kindergarten programs.
*   **Primary:** Link related to Primary education.
*   **Secondary:** Link related to Secondary education.
*   **Kindergarten:** Link specifically about Kindergarten.
*   **Primary School:** Link specifically about Primary School.
*   **Secondary School:** Link specifically about Secondary School.
*   **Primary (First cycle):** Link for the first cycle of Primary education admissions.

## Academic Areas

Links detailing the various academic subjects and educational projects offered.

*   **Academics:** Link to general academic information.
*   **Arts:** Link related to Arts programs.
*   **Science:** Link related to Science programs.
*   **Sports:** Link related to Sports programs.
*   **Social Skills:** Link related to Social Skills development.
*   **Educational Project:** Link for educational projects.
*   **Educational Proposal:** Link for educational proposals.

## Application and Process Links

Links facilitating the application process, interviews, and resource downloads.

*   **Work with us. Send CV:** Link for employment or CV submission.
*   **Padres - Legajos:** Link related to parent records/documents.
*   **Admission:** Link to the general admission page.
*   **Start Process:** Link to begin an application process.
*   **Interview:** Link related to scheduling or information about interviews.
*   **Calendar:** Link to view the school calendar.
*   **Download Brochure:** Link to download a school brochure.

## Alumni and External Resources

Links for alumni engagement, external systems, and language options.

*   **Alumni:** Link for alumni information.
*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to the school's webmail service.
*   **EN / English:** Language option for English content.
*   **Español:** Language option for Spanish content.

## School Information Links

Links related to specific informational topics and school identity.

*   **Administration:** Link related to the school administration.
*   **Webmail:** Link to webmail service (listed separately above).
*   **(no accessible label found on this element) (x2):** Unlabeled links present on the page.
*   **St. John's School:** Link referencing the school name.

## Staff and Custom Controls

Custom elements related to staff management.

*   **Staff (x2):** Custom controls likely used for staff-related interactions.
- stjohns.edu.ar/Web/{token}/Primary-School [Scouted, 56 components]
  Description: PRIMARY - Acquisition of both laguages is presented through a communicational globalized/whole language approach, presenting different types of texts to the children and stimulating their observation skills, their sense of comparison and their logical and critical thinking so that they may transfer 
  Components:
## Navigation and Admissions Links

This section contains links related to school admissions, educational levels, and application processes.

*   **Admissions:** Links for general admissions information, including specific links for Kinder, Primary, and Secondary levels, as well as links to start the process, view interviews, and download brochures.
*   **School Structure & Information:** Links providing details about the institution, such as "The School," "Institutional" details, "Our History," and "Agreements."
*   **Academic Areas:** Links detailing the school's focus areas, including Academics, Arts, Science, Sports, and Social Skills.
*   **Educational Programs:** Links related to specific educational initiatives, such as "Integral Formation" and options for submitting "Educational Project" or "Educational Proposal."
*   **School Levels:** Direct links for Primary School, Secondary School, Kindergarten, and Alumni information.
*   **Contact & Resources:** Links for administrative contacts ("Sites And Contacts"), historical documentation, and links to external resources like Moodle and Webmail.

## School Details and Staff Information

This section includes links providing specific details about the school and staff roles.

*   **Administration:** Links related to administration and contact information.
*   **Staff Directory:** Custom controls for viewing or interacting with staff information.

## Language Options

*   **Language Selection:** Links allowing users to switch the site language between English ("EN") and Spanish ("Español").
- stjohns.edu.ar/Web/{token}/Science [Scouted, 53 components]
  Description: SCIENCE - At St. John´s, students are encourged to discover and develp their potential within an environment prepared for integrated and intensive learning.
  Components:
## Navigation and Utility

*   **Toggle navigation:** Controls the visibility of the main website navigation menu.
*   **The School:** Link to the main page about the school.
*   **Institutional:** Link providing information about the institution.
*   **Our History:** Link detailing the school's history.
*   **Agreements:** Link containing agreements or policies.
*   **Sites And Contacts:** Link to a page listing sites and contact information.

## Admissions and Application Process

*   **Admissions (x3):** Links related to the admissions process.
*   **Kinder:** Link providing information about Kindergarten options.
*   **Primary:** Link providing information about Primary education.
*   **Secondary:** Link providing information about Secondary education.
*   **Primary (First cycle):** Link specific to the first cycle of Primary education entry.
*   **Admission:** Link to initiate an admission action.
*   **Start Process:** Link to begin the application process.
*   **Interview:** Link related to scheduling or information about interviews.
*   **Download Brochure:** Link to download a school brochure.

## School Level Links

*   **Kindergarten:** Link for Kindergarten information.
*   **Primary School:** Link for Primary School information.
*   **Secondary School:** Link for Secondary School information.

## Academic and Program Information

*   **Academics:** Link providing details on the school's academic programs.
*   **Arts:** Link related to the Arts curriculum or programs.
*   **Science:** Link related to Science programs.
*   **Sports:** Link related to Sports programs.
*   **Social Skills:** Link related to Social Skills development.
*   **Educational Project:** Link detailing educational projects.
*   **Educational Proposal:** Link providing educational proposals.

## School Information and Contact Links

*   **Admissions (x2):** Additional links related to admissions information.
*   **Administration:** Link for administrative information.
*   **Work with us. Send CV:** A link for potential employees to submit a CV.
*   **Padres - Legajos:** Link likely providing access to parent records or documents.
*   **Moodle:** Link to the Moodle learning platform.
*   **Webmail:** Link to the school's webmail service.
*   **St. John's School:** Link to the main school name page.
*   **Alumni:** Link for alumni information.
*   **Community:** Link related to the school community.
*   **Have you heard (x2):** Links soliciting feedback or information ("Have you heard").
*   **Calendar:** Link to the school calendar.

## Language Options

*   **EN:** Link for English language content.
*   **Español:** Link for Spanish language content.
*   **English:** Link for English language content.

## Unlabeled/Placeholder Links

*   **(no accessible label found on this element) (x2):** Two links without accessible labels.
- stjohns.edu.ar/Web/{token}/Social-Skills [Scouted, 53 components]
  Description: SOCIAL SKILLS - Studying at St. John´s means being part of a community which promotes social conscience and encourages our sudents to become committed members of whatever social group they belong to in the world.
  Components:
## Navigation and School Information

This section contains links for navigating specific school levels, admissions processes, and administrative information.

### Admissions and School Levels
*   **Admissions:** Link to admission information.
*   **Kinder:** Link related to Kindergarten information.
*   **Primary:** Link related to Primary level information.
*   **Secondary:** Link related to Secondary level information.
*   **Kindergarten:** Link to Kindergarten details.
*   **Primary School:** Link to Primary School details.
*   **Secondary School:** Link to Secondary School details.
*   **Alumni:** Link for alumni information.

### Admissions Process and Actions
*   **Start Process:** Link to start an application or admission process.
*   **Interview:** Link related to scheduling or information about interviews.
*   **Calendar:** Link to the school calendar.
*   **Download Brochure:** Link to download a brochure.

### Administration and Contact
*   **Administration:** Link for administrative details.
*   **Work with us. Send CV:** Link providing instructions or a form to send a CV.
*   **Padres - Legajos:** Link related to parent records.
*   **Sites And Contacts:** Link to general sites and contact information.

### Institutional and History
*   **The School:** Link providing information about the school itself.
*   **Institutional:** Link related to institutional details.
*   **Our History:** Link detailing the school's history.
*   **Agreements:** Link related to agreements.

## Academic Programs and Subjects

This section provides links to various academic areas and educational projects offered by the school.

*   **Academics:** Link to general academic information.
*   **Arts:** Link related to arts programs.
*   **Science:** Link related to science programs.
*   **Sports:** Link related to sports programs.
*   **Social Skills:** Link related to social skills education.
*   **Integral Formation:** Link related to integral formation programs.
*   **Educational Project:** Link to educational projects.
*   **Educational Proposal:** Link related to educational proposals.

## School Identity and Links

*   **St. John's School:** Link identifying the school.
*   **Webmail:** Link to webmail services.
*   **Moodle:** Link to Moodle platform.
*   **(no accessible label found on this element):** An unlabelled link.
*   **(no accessible label found on this element):** An unlabelled link.

## Language Options

*   **EN:** Link for English language options.
*   **Español:** Link for Spanish language options.
*   **English:** Link for English language options.

## Navigation Control

*   **Toggle navigation:** Button used to toggle the main navigation menu.
- stjohns.edu.ar/Web/{token}/Sports [Scouted, 53 components]
  Description: SPORTS - Education is not limited to academic preparation. St. John´s therefore provides integrated learing experiences which strengthen children´s personalities, thus empowering them to become exemplary members and leaders of the society in which they live.
  Components:
## Navigation and School Programs

This section contains links for navigating different sections of the school website, focusing on educational levels and programs:

*   **Admissions:** Links related to application processes, including general admissions, kindergarten, primary, and secondary school admissions.
*   **Educational Programs:** Links providing information on various academic subjects and developmental areas, such as Arts, Science, Sports, Social Skills, Integral Formation, Academics, and Educational Projects/Proposals.
*   **School Levels:** Specific links for Kindergarten, Primary School, and Secondary School.
*   **Alumni & Community:** Links related to Alumni information and Community engagement.

## Institutional Information

These links provide details about the school itself:

*   **About the School:** Links detailing the institution, our history, agreements, and sites and contacts.
*   **School Identity:** A link referencing "St. John's School."

## Application and Contact

Links related to prospective students and administrative actions:

*   **Admissions Process:** Links for starting the admission process, viewing interview information, and accessing calendars or brochures.
*   **Contact & Systems:** Links for contacting the school, downloading brochures, viewing sites and contacts, and links to Moodle and Webmail systems.

## Administrative and System Links

Links providing access to administrative functions and internal resources:

*   **Administration:** A link related to school administration.
*   **Work with us:** A link prompting users to send a CV.

## Language Options

Links allowing the user to switch the website language:

*   English (EN)
*   Español
*   English

## Digital Blueprint Summary: St. John's Educational Portal

This section of the website documents the educational offerings and institutional framework of St. John's, focusing on its holistic approach to education, structured across various academic levels and defined by specific educational focus areas.

The pages collectively serve as the central hub for prospective students, parents, alumni, and the community, providing detailed information on admissions, educational philosophy, school history, and practical resources.

### Core Educational Structure

The site is organized around the following key educational levels:

*   **Primary Education (`/primaria`):** Focuses on a communicative learning approach, emphasizing contact with different texts and expression across various media.
*   **Secondary Education (`/secundaria`):** Aims for academic excellence by combining autonomous work with analytical capacity to foster integral individuals.
*   **Sport/Physical Education (`/deportiva`):** Highlights the school's commitment to developing students holistically, extending beyond academics.

### Institutional Framework and Focus Areas

All sections are unified by a consistent set of institutional links and educational pillars, which define the school's philosophy:

**Educational Pillars:** The curriculum is structured around comprehensive development, including:
*   Humana (Humanistic studies)
*   Académica (Academic subjects)
*   Artística (Artistic studies)
*   Científica (Scientific studies)
*   Deportiva (Sports and Physical Education)

**Institutional Information:** Users can access detailed information about the school through links covering:
*   **History and Identity:** Nuestra Historia, El Colegio, Institucional.
*   **Community & Partnerships:** Comunidad, Convenios y Alianzas.
*   **Resources:** Padres - Legajos (Parent records), Alumni, y FAQs ($\text{¿Sabías qué?}$).

### Application and Process Links

The site provides clear pathways for engagement with the school:
*   **Admissions Process:** Links are available to initiate applications ($\text{Iniciar proceso}$), schedule interviews ($\text{Entrevista}$), view calendars ($\text{Calendario}$), and download brochures ($\text{Descargar Folleto}$).
*   **Resources:** External educational platforms (Moodle) and communication tools (Webmail) are linked.

### Language Options

The website supports multilingual access, offering options in Spanish ($\text{ES/Español}$) and English.

## Digital Blueprint: St. John's School Web Section

This section of the website is dedicated to providing comprehensive information about St. John's School, focusing on admissions, educational philosophy, institutional history, and alumni relations.

### Overview

The central hub for this section is the main web page (`/web`), which establishes the school's mission: "Desarrollamos la confianza, la independencia y la autoestima de los niños a través del juego, su mayor fuente de aprendizaje." This page serves as the primary navigation point linking users to all facets of the school.

### Navigation and Structure

The site structure is organized around several key themes:

1.  **Admissions and Levels:** Information is provided for various educational stages, including Kinder, Primary (Primer ciclo), Secondary education, and general admission processes.
2.  **Educational Focus Areas:** The curriculum and philosophy are broken down into specific focus areas, such as *Científica* (Science), *Artística* (Arts), *Deportiva* (Sports), *Humana* (Humanistic studies), and *Social Skills*.
3.  **Institutional Information:** Links are available for detailed institutional details, including the school's history (*Nuestra Historia*), agreements (*Convenios*), and contact information.
4.  **Alumni Relations:** A dedicated section focuses on alumni engagement, featuring updates on alumni stories (*¿Sabías qué?*) and links to specific alumni records (e.g., Clara Benadiba, Francisco Bosch).

### Specific Routes

The blueprint also includes routes for specific educational components, although they currently return a "Server Error" status:

*   `/Web/{token}/{token}/Science`
*   `/Web/{token}/{token}/Social-Skills`
*   `/Web/{token}/{token}/Sports`

These routes suggest specific content pages related to the defined educational focus areas.

_(section summary unavailable: Response truncated: the model hit max_tokens before finishing (finish_reason: 'length'). This is almost always max_tokens set too low for a reasoning model's chain-of-thought - raise agents.local.max_tokens (or LOCAL_MAX_TOKENS) in pragma.yaml/.env and try again, or unset it entirely to let the model use as much as it needs.)_

- stjohns.edu.ar/web/Alumni/Sabias-Que [Scouted, 168 components]
  Description: ¿Sabías qué? - Las historias de nuestros exalumnos se actualizan mensualmente.
Si querés recibir la newsletter por favor escribinos a news@stjohns.edu.ar
  Components:
## Navigation and Controls

**Close Button**
A button used to close the current view or panel.

**Toggle navigation**
A button used to toggle the visibility of the main navigation menu.

## Admissions and Educational Programs

**Admission Links**
Links providing access to admission information:
*   Admisiones (Multiple instances)
*   Kinder
*   Primaria
*   Secundaria
*   Primaria (Primer ciclo)

**Educational Focus Areas**
Links detailing the educational focus areas:
*   Formación Integral
*   Académica
*   Artística
*   Científica
*   Deportiva
*   Humana

**Program Links**
Links related to specific educational levels:
*   Kindergarten
*   Educación Primaria
*   Educación Secundaria

## Institutional Information and History

**School Identity**
*   St. John's School (Link)

**Institutional Details**
*   El Colegio (Link)
*   Institucional (Link)
*   Nuestra Historia (Link)
*   Convenios (Link)
*   Sedes y Contacto (Link)
*   ¿Sabías qué? (Multiple instances)

## Alumni and Community

**Alumni Information**
*   Alumni (Link)
*   Comunidad (Link)

## Application and Process Actions

Links for initiating processes:
*   Admisión (Link)
*   Iniciar proceso (Link)
*   Entrevista (Link)
*   Calendario (Link)
*   Descargar Folleto (Link)

## Language Selection

Links for switching the language of the page:
*   ES (Spanish)
*   Español
*   English

## Alumni Profiles

A list of alumni entries, each linking to a profile:
*   CLARA BENADIBA (2017)
*   FRANCISCO BOSCH (1983)
*   IVÁN CUENCA (1998)
*   RODRIGO TEIJEIRO (1995)
*   MARCOS MAFÍA DEL CASTILLO (2006)
*   LUCAS CAMACHO / GONZALO DELGUY (2003)
*   CÉSAR BUSTOS (1996)
- stjohns.edu.ar/web/El-Colegio/Convenios [Scouted, 61 components]
  Description: CONVENIOS Y ALIANZAS - Promovemos lazos y convenios con las principales instituciones educativas de habla inglesa, manteniendo un nivel de formación bajo los más altos estándares mundiales. Contamos con convenios con las más prestigiosas universidades privadas nacionales para el ingreso directo de n
  Components:
## Navigation and School Information Links

This section includes links for navigating the website and accessing general institutional information.

*   **Admisiones:** Links related to admissions processes.
*   **Kinder:** Link for Kindergarten information.
*   **Primaria:** Link for Primary education information.
*   **Secundaria:** Link for Secondary education information.
*   **Admisiones (Repeated):** Another link related to admissions.
*   **Kinder (Repeated):** Another link related to Kindergarten.
*   **Primaria (Primer ciclo):** Link for information regarding the first cycle of Primary education.
*   **Padres - Legajos:** Link likely leading to parent records or files.
*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to the webmail service.
*   **St. John's School:** Link potentially leading to the school's main page.
*   **El Colegio:** Link about the school itself.
*   **Institucional:** Link for institutional information.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Convenios:** Link related to agreements or partnerships.
*   **Sedes y Contacto (Repeated):** Links related to locations and contact details.
*   **¿Sabías qué?:** Links to general trivia or interesting facts.
*   **Formación Integral:** Link concerning integral education.
*   **Académica:** Link related to academic matters.
*   **Artística:** Link for artistic subjects.
*   **Científica:** Link for scientific subjects.
*   **Deportiva:** Link for sports/physical education.
*   **Humana:** Link for humanities subjects.
*   **Proyecto Educativo:** Link to the educational project.
*   **Propuesta Educativa:** Link to the educational proposal.
*   **Kindergarten:** Link for Kindergarten information (English).
*   **Educación Primaria:** Link for Primary education information (English).
*   **Educación Secundaria:** Link for Secondary education information (English).
*   **Alumni:** Link for alumni information.
*   **Comunidad:** Link related to the school community.
*   **¿Sabías qué? (Repeated):** Another link to general trivia or interesting facts.

## Application and Process Links

These links guide users through the application and inquiry process.

*   **Admisión:** Link to start the admission process.
*   **Iniciar proceso:** Link to begin an application process.
*   **Entrevista:** Link related to interviews.
*   **Calendario:** Link to view the school calendar.
*   **Descargar Folleto:** Link to download a brochure or flyer.

## Language Links

*   **Español:** Link to the Spanish version of the content.
*   **English:** Link to the English version of the content.

## Custom Programmatic Controls (Diplomas and Alliances)

These components likely represent specific educational programs or alliances offered by the school.

*   **IB DIPLOMA:** A custom control related to the IB Diploma program.
*   **IB DIPLOMA (Repeated):** Another instance related to the IB Diploma program.
*   **ALIANZA FRANCESA:** A custom control related to the French Alliance.
*   **ALIANZA FRANCESA (Repeated):** Another instance related to the French Alliance.
*   **UNIVERSIDAD DE SAN ANDRÉS:** A custom control related to the University of San Andrés.
*   **UNIVERSIDAD DE SAN ANDRÉS (Repeated):** Another instance related to the University of San Andrés.
*   **UNIVERSIDAD TORCUATO DI TELLA:** A custom control related to the Tortuato di Tella University.
*   **UNIVERSIDAD TORCUATO DI TELLA (Repeated):** Another instance related to the Tortuato di Tella University.
*   **UNIVERSIDAD AUSTRAL:** A custom control related to the Universidad Austral.
- stjohns.edu.ar/web/El-Colegio/convenios [Scouted, 61 components]
  Description: CONVENIOS Y ALIANZAS - Promovemos lazos y convenios con las principales instituciones educativas de habla inglesa, manteniendo un nivel de formación bajo los más altos estándares mundiales. Contamos con convenios con las más prestigiosas universidades privadas nacionales para el ingreso directo de n
  Components:
## Navigation Menu

### Admissions & School Information
*   **Admisiones:** Navigates to information regarding admissions.
*   **Kinder:** Navigates to information about Kindergarten.
*   **Primaria:** Navigates to information about Primary education.
*   **Secundaria:** Navigates to information about Secondary education.
*   **Admisiones (Repeated):** Another link for admission information.
*   **Kinder (Repeated):** Another link for Kindergarten information.
*   **Primaria (Primer ciclo):** Navigates to information specifically about the Primary cycle.
*   **Padres - Legajos:** Accesses information related to parents and records.

### Institutional & Historical Information
*   **El Colegio:** Link related to the school itself.
*   **Institucional:** Navigates to institutional information.
*   **Nuestra Historia:** Provides the school's history.
*   **Convenios:** Displays information about agreements or partnerships.
*   **Sedes y Contacto:** Links to location details and contact information (appears multiple times).
*   **¿Sabías qué?:** Accesses interesting facts.
*   **Formación Integral:** Information regarding integral education.
*   **Académica:** Navigates to academic information.
*   **Artística:** Information about artistic programs.
*   **Científica:** Information about scientific programs.
*   **Deportiva:** Information about sports/physical education.
*   **Humana:** Information about humanistic studies.
*   **Proyecto Educativo:** Details about the educational project.
*   **Propuesta Educativa:** Details about the educational proposal.
*   **Kindergarten:** Link related to Kindergarten programs.
*   **Educación Primaria:** Link related to Primary education.
*   **Educación Secundaria:** Link related to Secondary education.
*   **Alumni:** Information for former students.
*   **Comunidad:** Information about the school community.

### External Links & Resources
*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to webmail services.
*   **St. John's School:** Link to information about St. John's School.
*   **El Colegio:** Link to the school name/homepage.

### Actions & Downloads
*   **Admisión:** Initiates the admission process.
*   **Iniciar proceso:** Starts the application process.
*   **Entrevista:** Accesses interview information.
*   **Calendario:** Displays the school calendar.
*   **Descargar Folleto:** Allows downloading of a brochure/leaflet.

### Language Selection
*   **ES:** Selects Spanish language.
*   **Español:** Selects Spanish language.
*   **English:** Selects English language.

## Custom Program Selections
These components appear to select specific diploma or alliance programs:
*   **IB DIPLOMA (First instance):** Selection option for the IB Diploma program.
*   **IB DIPLOMA (Second instance):** Another selection option for the IB Diploma program.
*   **ALIANZA FRANCESA (First instance):** Selection option for the French Alliance program.
*   **ALIANZA FRANCESA (Second instance):** Another selection option for the French Alliance program.
*   **UNIVERSIDAD DE SAN ANDRÉS (First instance):** Selection option related to the University of San Andrés.
*   **UNIVERSIDAD DE SAN ANDRÉS (Second instance):** Another selection option related to the University of San Andrés.
*   **UNIVERSIDAD TORCUATO DI TELLA (First instance):** Selection option related to the University Torcuato Di Tella.
*   **UNIVERSIDAD TORCUATO DI TELLA (Second instance):** Another selection option related to the University Torcuato Di Tella.
*   **UNIVERSIDAD AUSTRAL:** Selection option related to the University Austral.
- stjohns.edu.ar/web/Sedes-Contacto [Scouted, 78 components]
  Description: SEDES Y CONTACTO - Panamericana Km. 48.800
  Components:
## Navigation and School Information Links

This section groups links related to admissions processes, educational levels, and general school information.

### Admissions and Grade Levels
*   **Admisiones:** Link to admission information.
*   **Kinder:** Link related to Kindergarten information.
*   **Primaria:** Link related to Primary education.
*   **Secundaria:** Link related to Secondary education.
*   **Primaria (Primer ciclo):** Link specifically for the Primary (First cycle) level.

### Academic and Program Information
*   **Formación Integral:** Link regarding integral education.
*   **Académica:** Link concerning academic matters.
*   **Artística:** Link related to artistic programs.
*   **Científica:** Link related to scientific programs.
*   **Deportiva:** Link related to sports programs.
*   **Humana:** Link related to humanities programs.
*   **Proyecto Educativo:** Link regarding the educational project.
*   **Propuesta Educativa:** Link regarding the educational proposal.

### School and Institutional Details
*   **El Colegio:** Link referring to the school itself.
*   **Institucional:** Link for institutional information.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Convenios:** Link concerning agreements or partnerships.
*   **Sedes y Contacto:** Link related to locations and contact details.
*   **Sedes y Contacto (Repeated):** Another link providing location and contact information.

### Alumni and Community
*   **Alumni:** Link for alumni information.
*   **Comunidad:** Link concerning the school community.

### Frequently Asked Questions
*   **¿Sabías qué?:** Links to various informational Q&A sections.

## Administrative and External Links

This section groups links related to specific processes, external resources, and contact methods.

### Application and Process Steps
*   **Admisión:** Link related to the admission process.
*   **Iniciar proceso:** Link to start an application process.
*   **Entrevista:** Link related to scheduling or information about interviews.
*   **Calendario:** Link to view the school calendar.
*   **Descargar Folleto:** Link to download a brochure.

### External Resources and Contact
*   **Moodle:** Link to Moodle platform resources.
*   **Webmail:** Link to webmail access.
*   **Ver en Google Maps (Multiple instances):** Links to view the location on Google Maps.
*   **Whatsapp admisiones:** Link for contacting admissions via WhatsApp.

### School Branding and Other Links
*   **St. John's School:** Link referencing the school name.
*   **Ver en Google Maps:** Another link to view the location on Google Maps.
*   **(no accessible label found on this element) (Multiple instances):** Hidden text fields present on the page.
- stjohns.edu.ar/web/The-school/Agreements [Scouted, 63 components]
  Description: AGREEMENTS AND JOINT VENTURES - We have established ties with the main English speaking educational institutions and share sports and cultural activities with them. Our academic standards are in accordance with the highest world standards. Agreements signed with prestigious, private Argentine univer
  Components:
## Navigation and School Information Links

This section groups the links found on the page, categorized by their function.

### Admissions and School Levels
These links relate to different stages of school enrollment and admission processes.

*   **Admissions:** Link leading to general admissions information.
*   **Kinder:** Link related to Kindergarten information.
*   **Primary:** Link related to Primary school information.
*   **Secondary:** Link related to Secondary school information.
*   **Primary (First cycle):** Link specifically for the first cycle of Primary education.
*   **Kindergarten:** Link related to Kindergarten details.
*   **Primary School:** Link related to Primary School details.
*   **Secondary School:** Link related to Secondary School details.
*   **Alumni:** Link related to alumni information.

### Academic and Program Information
These links direct users to detailed information about the school's offerings and history.

*   **Academics:** Link providing academic details.
*   **Arts:** Link providing information about Arts programs.
*   **Science:** Link providing information about Science programs.
*   **Sports:** Link providing information about Sports programs.
*   **Social Skills:** Link providing information about Social Skills development.
*   **Integral Formation:** Link related to integral formation programs.
*   **Educational Project:** Link providing details on educational projects.
*   **Educational Proposal:** Link providing access to educational proposals.
*   **Our History:** Link detailing the school's history.

### Contact, Sites, and Outreach
These links relate to contact information, external resources, and community engagement.

*   **Sites And Contacts:** Link providing general sites and contact information.
*   **Have you heard:** Link related to hearing or accessing specific information (appears twice).
*   **Community:** Link related to the school's community.
*   **Webmail:** Link to access webmail services.
*   **Moodle:** Link to Moodle platform resources.

### Action and Process Links
These links guide users through interactive processes, applications, and downloads.

*   **Start Process:** Link to initiate an application or process.
*   **Interview:** Link related to interview scheduling or information.
*   **Calendar:** Link to view the school calendar.
*   **Download Brochure:** Link to download a brochure.
*   **Work with us. Send CV:** Link for job applications or sending a Curriculum Vitae.

### Language Options
Links allowing users to view content in different languages.

*   **EN:** Link for English language content.
*   **Español:** Link for Spanish language content.
*   **English:** Link for English content.

### Custom Control/Diploma Links
These links appear to be specific diploma or affiliation options.

*   **IB DIPLOMA (x2):** Links related to the IB Diploma program.
*   **ALLIANCE FRANÇAISE (x2):** Links related to the Alliance Française affiliation.
*   **SAINT ANDREWS´S UNIVERSITY (x2):** Links related to Saint Andrews University affiliation.
*   **TORCUATO DI TELLA UNIVERSITY:** Link related to Tortuato di Tella University.

### Unlabeled/Placeholder Elements
These elements are present but lack accessible labels.

*   Two hidden text fields without accessible labels.
*   Two links with no accessible label.

## Section 3

_(chunk combine unavailable: Local API Error (400): {"error":"Engine protocol predict request returned 400: {\"error\":{\"code\":400,\"message\":\"request (8592 tokens) exceeds the available context size (4096 tokens), try increasing it\",\"type\":\"exceed_context_size_error\",\"n_prompt_tokens\":8592,\"n_ctx\":4096}}"})_

## Digital Blueprint: School History and Educational Partnerships

This section of the website documents the historical narrative, institutional structure, and educational partnerships of St. John's School (`stjohns.edu.ar`). The pages connect the school's history with its current academic offerings, admissions processes, and international alliances.

### Overview

The linked pages serve two primary functions: providing a contextual history of the institution and detailing the specific educational programs, curriculum areas, and external agreements that define the school’s educational philosophy.

### Page Breakdown and Relationship

#### 1. Our History (`/web/The-school/Our-History`)
This page establishes the institutional context by focusing on the bond between students and the school. It acts as a foundational entry point, providing general navigation to various sections of the school (Admissions, Academic areas, Institutional information) and links to administrative actions (CV submission, Alumni, Moodle). It allows users to navigate through historical periods (e.g., 1950, 1960) and switch between English and Spanish languages.

#### 2. Agreements/Partnerships (`/web/el-colegio/convenios`)
This page details the external relationships and educational alliances of the school. It highlights partnerships with English-speaking institutions and national universities. This section is highly structured, providing detailed information on:
*   **Educational Levels:** Links for Kindergarten, Primary, and Secondary education.
*   **Curriculum Focus:** Information categorized by academic disciplines (Artística, Científica, Deportiva, Humana).
*   **Application Process:** Steps related to admission, starting the application process, and interviews.
*   **External Alliances:** Specific selection controls for partnerships with entities like the IB Diploma, the University of San Andrés, and the University of Torcuato Di Tella.
*   **Resources:** Links to Moodle and Webmail for educational resources.

### Summary of Flow

The structure flows from **Historical Context** (Our History) to **Specific Educational Structure and External Commitments** (Convenios). The first page provides the "who" and "when" of the school's journey, while the second page details the specific programs, curriculum choices, and international frameworks that define the current educational opportunities offered by St. John's School.

_(section summary unavailable: Response truncated: the model hit max_tokens before finishing (finish_reason: 'length'). This is almost always max_tokens set too low for a reasoning model's chain-of-thought - raise agents.local.max_tokens (or LOCAL_MAX_TOKENS) in pragma.yaml/.env and try again, or unset it entirely to let the model use as much as it needs.)_

- stjohns.edu.ar/web/el-colegio/{token} [Scouted, 63 components]
  Description: Nuestra historia - La relación entre un alumno y su colegio no termina el último día de clases. El lugar y las personas que contribuyeron a la formación de un individuo pasan a formar parte de él.
  Components:
## Navigation and Pagination

This section contains controls for navigating through content, likely related to historical data or sequential pages.

*   **Previous / Next Links:** Standard links used to navigate backward and forward between content sections.
*   **Year Tabs:** Selectable tabs allowing navigation between specific years (e.g., 1950, 1960).

## Main Navigation

These links provide access to major sections of the website or specific institutional information.

*   **School Links:** Links to core institutional information such as "El Colegio" and "Institucional."
*   **History and Relations:** Links providing historical context ("Nuestra Historia") and external relations ("Convenios").
*   **Contact and Location:** Links related to physical location and contact details ("Sedes y Contacto").
*   **General Information:** Links offering general information like "¿Sabías qué?" and "Formación Integral."

## Educational Programs and Admissions

This group consists of links detailing the various educational levels offered by the school, often categorized by level and admission status.

*   **Admission/Application Links:** Links related to applying for admission ("Admisiones," "Iniciar proceso," "Entrevista").
*   **Grade Level Links:** Links providing information specific to different educational stages:
    *   Kindergarten
    *   Primaria (Primer ciclo)
    *   Educación Primaria
    *   Secundaria
*   **Specific Program Links:** Links related to specific areas of study or student records, including "Admisiones," "Kinder," "Primaria," "Secundaria," and links for "Padres - Legajos" (Parents - Records).

## External Resources and Media

These components link to external systems or media resources.

*   **External Systems:** Links directing users to external platforms such as Moodle and Webmail.
*   **School Branding:** A link referencing the school name ("St. John's School").
*   **Language Options:** Links for switching content language, including Español, English, and potentially other languages (e.g., "English").

## Form/Document Access

Links providing access to specific downloadable documents or detailed information.

*   **Documents:** Links to download materials, such as "Descargar Folleto" (Download Brochure).
*   **Specific Records:** Links related to accessing student records ("Padres - Legajos").
- stjohns.edu.ar/web/sites-contacts [Scouted, 79 components]
  Description: SITES AND CONTACTS - Panamericana Km. 48.800
  Components:
## Navigation and School Information

This section groups links related to navigating the website structure and accessing specific school information.

### Main Navigation Links
*   **Admissions:** Link to admissions information.
*   **Kinder:** Link to kindergarten information.
*   **Primary:** Link to primary school information.
*   **Secondary:** Link to secondary school information.
*   **Admissions (Repeat):** Another link related to admissions.
*   **Kinder (Repeat):** Another link related to kindergarten.
*   **Primary (First cycle):** Link specifically for the first cycle of primary education.
*   **Administration:** Link related to school administration.
*   **Work with us. Send CV:** A link prompting users to send a CV or connect regarding employment.
*   **Padres - Legajos:** A link likely for parents accessing records.
*   **Moodle:** Link to the Moodle learning platform.
*   **Webmail:** Link related to webmail access.
*   **St. John's School:** Link to information about St. John's School.

### Institutional and History Links
*   **The School:** Link providing general information about the school.
*   **Institutional:** Link to institutional details.
*   **Our History:** Link detailing the school's history.
*   **Agreements:** Link related to agreements.
*   **Sites And Contacts:** Link to the sites and contacts section.

### Academic and Program Links
*   **Integral Formation:** Information regarding integral formation.
*   **Academics:** General academics information.
*   **Arts:** Information about arts programs.
*   **Science:** Information about science programs.
*   **Sports:** Information about sports programs.
*   **Social Skills:** Information related to social skills development.
*   **Educational Project:** Details about educational projects.
*   **Educational Proposal:** Information regarding educational proposals.
*   **Kindergarten:** Link specifically for kindergarten.
*   **Primary School:** Link specifically for primary school.
*   **Secondary School:** Link specifically for secondary school.

### Admissions Process Links
*   **Have you heard:** A link related to hearing or receiving information.
*   **Admission:** Link related to the admission process.
*   **Start Process:** A link to begin an application or admission process.
*   **Interview:** Link related to scheduling or information about interviews.
*   **Calendar:** Link to the school calendar.
*   **Download Brochure:** Link to download a brochure.

### Contact and Utility Links
*   **View in Google Maps:** Link to view the location on Google Maps.
*   **Send email:** Link to initiate sending an email.
*   **Sites And Contacts (Repeat):** Another link to sites and contacts.

### Language Options
*   **EN:** Link for English language options.
*   **Español:** Link for Spanish language options.
*   **English:** Link specifically for the English language.

## Hidden Fields
*   Two hidden text fields exist on the page, without visible labels.
- stjohns.edu.ar/web/the-school/agreements [Scouted, 63 components]
  Description: AGREEMENTS AND JOINT VENTURES - We have established ties with the main English speaking educational institutions and share sports and cultural activities with them. Our academic standards are in accordance with the highest world standards. Agreements signed with prestigious, private Argentine univer
  Components:
## Navigation and School Levels

This section contains links guiding users to specific admissions or school level information.

*   **Admissions:** Links related to applying for admission.
*   **Kinder:** Links related to Kindergarten programs.
*   **Primary:** Links related to Primary school options.
*   **Secondary:** Links related to Secondary school options.
*   **Admissions (Repeated):** Additional links pertaining to admissions.
*   **Kinder (Repeated):** Additional links pertaining to Kindergarten.
*   **Primary (First cycle):** A specific link for the first cycle of Primary education.

## School Information and History

These links provide details about the institution, its history, and operational information.

*   **The School:** Link providing general information about the school.
*   **Institutional:** Information regarding the school's institutional details.
*   **Our History:** Access to the school's history.
*   **Agreements:** Information regarding agreements.
*   **Sites And Contacts:** Links for finding sites and contact information.

## Academic Programs and Curriculum

Links detailing the educational offerings and curriculum areas.

*   **Integral Formation:** Information on integral formation programs.
*   **Academics:** Details about academic subjects.
*   **Arts:** Information regarding arts programs.
*   **Science:** Information regarding science programs.
*   **Sports:** Information regarding sports programs.
*   **Social Skills:** Information regarding social skills development.

## School Level Links

Links specifically targeting information for different educational stages.

*   **Kindergarten:** Link to Kindergarten information.
*   **Primary School:** Link to Primary School information.
*   **Secondary School:** Link to Secondary School information.
*   **Alumni:** Information for former students or alumni.

## Application and Contact Actions

Links prompting users to take action, apply, or contact the school.

*   **Work with us. Send CV:** A link to submit a CV or inquire about employment opportunities.
*   **Padres - Legajos:** Access to parent records/files.
*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to the school's webmail service.
*   **Admission:** General link related to admission processes.
*   **Start Process:** A link to begin an application process.
*   **Interview:** A link related to scheduling or information about interviews.
*   **Calendar:** Access to the school calendar.
*   **Download Brochure:** Link to download a brochure.

## General Navigation Links

Miscellaneous links found on the page.

*   **(No accessible label found on this element):** Unlabeled link.
*   **(No accessible label found on this element):** Unlabeled link.

## Language Options

Links allowing users to switch the language of the page.

*   **EN:** Link for English.
*   **Español:** Link for Spanish.
*   **English:** Link for English (repeated).

## Custom Control Labels (Diplomas/Universities)

These components appear to be labels or links related to specific diploma or university affiliations.

*   **IB DIPLOMA:** A custom control related to the IB Diploma.
*   **IB DIPLOMA (Repeated):** Another instance of the IB Diploma label.
*   **ALLIANCE FRANÇAISE:** A custom control related to the Alliance Française.
*   **ALLIANCE FRANÇAISE (Repeated):** Another instance of the Alliance Française label.
*   **SAINT ANDREWS´S UNIVERSITY:** A custom control related to Saint Andrews University.
*   **SAINT ANDREWS´S UNIVERSITY (Repeated):** Another instance of the Saint Andrews University label.
*   **TORCUATO DI TELLA UNIVERSITY:** A custom control related to Torcuato di Tella University.

## Page Control

*   **Toggle navigation:** A button used to toggle the main navigation menu.
- stjohns.edu.ar/web/{token}/Artistica [Scouted, 57 components]
  Description: FORMACIÓN ARTÍSTICA - St. John's ofrece una experiencia viva y dinámica que complementa la cultura general de los alumnos. Estudiar en St. John's es tener acceso a las mejores herramientas para desarrollar tu potencial y superarte día a día.
  Components:
## Navigation and School Information Links

### Admissions and Academic Levels
These links provide access to information regarding school admissions and different educational levels.

*   **Admisiones:** Links related to admissions procedures.
*   **Kinder:** Links related to kindergarten information.
*   **Primaria:** Links related to primary education.
*   **Secundaria:** Links related to secondary education.
*   **Primaria (Primer ciclo):** Link specifically for the primary cycle.
*   **Admisión:** Link to start the admission process.
*   **Entrevista:** Link related to interviews.
*   **Calendario:** Link to view the calendar.
*   **Descargar Folleto:** Link to download a brochure.

### Academic and Program Links
These links direct users to specific academic areas, educational proposals, and historical information.

*   **Artística:** Link for artistic subjects.
*   **Científica:** Link for scientific subjects.
*   **Deportiva:** Link for sports-related information.
*   **Humana:** Link for humanities subjects.
*   **Proyecto Educativo:** Link to view the educational project.
*   **Propuesta Educativa:** Link to view the educational proposal.

### School and Institutional Information
These links provide details about the school, its history, and administrative contacts.

*   **St. John's School:** Link to the main school information page.
*   **El Colegio:** Link for general school information.
*   **Institucional:** Link for institutional details.
*   **Nuestra Historia:** Link to view the school's history.
*   **Convenios:** Link for agreements or treaties.
*   **Sedes y Contacto:** Link for locations and contact information (appears multiple times).
*   **Comunidad:** Link related to the school community.

### Administrative and Resource Links
These links provide access to external resources, alumni data, and administrative portals.

*   **Padres - Legajos:** Link related to parents' records.
*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to the webmail service.
*   **Alumni:** Link for alumni information.

### Informational and Utility Links
These links provide general information, FAQs, and language options.

*   **¿Sabías qué?:** Links containing general trivia or interesting facts (appears multiple times).
*   **Formación Integral:** Link related to integral education.
*   **Académica:** Link for academic details.
*   **Español:** Language selection for Spanish.
*   **English:** Language selection for English.
- stjohns.edu.ar/web/{token}/Cientifica [Scouted, 51 components]
  Description: FORMACIÓN CIENTÍFICA - St. John's estimula a los alumnos a descubrir y desarrollar su potencial al más alto nivel en un ambiente apto para una educación intensiva e integral.
  Components:
## Navigation and School Information Links

This section groups links related to navigation, institutional information, and school programs.

### Main Menu / Navigation
*   **Toggle navigation:** Button used to show or hide the main navigation menu.
*   **El Colegio:** Link to information about the school.
*   **Institucional:** Link to institutional information.
*   **Nuestra Historia:** Link providing the school's history.
*   **Convenios:** Link to information regarding agreements/partnerships.
*   **Sedes y Contacto:** Link providing location and contact details.

### Academic Programs and Areas
This section includes links detailing different educational tracks, cycles, and focus areas.
*   **Admisiones:** Links related to the admission process.
*   **Kinder:** Link for Kindergarten information.
*   **Primaria (Primer ciclo):** Link for Primary education (First cycle).
*   **Educación Primaria:** Link for Primary education.
*   **Educación Secundaria:** Link for Secondary education.
*   **Kindergarten:** Link for Kindergarten.
*   **Académica:** Link related to academic matters.
*   **Artística:** Link related to artistic subjects.
*   **Científica:** Link related to scientific studies.
*   **Deportiva:** Link related to sports/physical education.
*   **Humana:** Link related to humanistic studies.

### School Identity and Community
*   **St. John's School:** Link to the main school page.
*   **Alumni:** Link for alumni information.
*   **Comunidad:** Link related to the school community.
*   **Proyecto Educativo:** Link detailing the educational project.
*   **Propuesta Educativa:** Link detailing the educational proposal.

### Administrative and Contact Links
*   **Padres - Legajos:** Link for parents' records/files.
*   **¿Sabías qué?:** Links providing interesting facts.
*   **Webmail:** Link to the school's webmail service.
*   **Moodle:** Link to the Moodle platform.

### Language Options
*   **Español:** Link to the Spanish language version.
*   **English:** Link to the English language version.

### Action Links (Admissions Process)
These links guide users through specific application or information requests.
*   **Admisión:** General link for admission.
*   **Iniciar proceso:** Link to start a process.
*   **Entrevista:** Link related to interviews.
*   **Calendario:** Link to the school calendar.
*   **Descargar Folleto:** Link to download a brochure.

_(section summary unavailable: Response truncated: the model hit max_tokens before finishing (finish_reason: 'length'). This is almost always max_tokens set too low for a reasoning model's chain-of-thought - raise agents.local.max_tokens (or LOCAL_MAX_TOKENS) in pragma.yaml/.env and try again, or unset it entirely to let the model use as much as it needs.)_

- stjohns.edu.ar/web/{token}/Humana [Scouted, 51 components]
  Description: FORMACIÓN HUMANA - Estudiar en St. John's es formar parte de una comunidad donde promovemos la conciencia social e impulsamos a nuestros alumnos a asumir un compromiso con el mundo en que viven desde el lugar que ocupan.
  Components:
## Navigation and Admissions Links

This section contains links related to school admissions, educational levels, and administrative processes.

*   **Admisiones:** Links related to admission procedures.
*   **Kinder:** Link for Kindergarten information.
*   **Primaria:** Link for Primary education information.
*   **Secundaria:** Link for Secondary education information.
*   **Admisiones (Repeated):** Additional links regarding admissions.
*   **Kinder (Repeated):** Additional links regarding Kindergarten.
*   **Primaria (Primer ciclo):** Link specifically for the Primary cycle.
*   **Padres - Legajos:** Link related to parent records or files.
*   **Admisión:** Link to start the admission process.
*   **Iniciar proceso:** Link to begin a specific process.
*   **Entrevista:** Link related to interviews.
*   **Calendario:** Link to view the school calendar.
*   **Descargar Folleto:** Link to download a brochure.
*   **Sedes y Contacto (Repeated):** Links for locations and contact information.
*   **ES:** Link related to ES (likely a specific program or section).
*   **Español:** Link for the Spanish language version.
*   **English:** Link for the English language version.

## Institutional Information and Programs

This group includes links providing details about the school, its history, educational focus, and community aspects.

*   **St. John's School:** Link to the main school page.
*   **El Colegio:** Link related to the school body or structure.
*   **Institucional:** Link for institutional information.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Convenios:** Links regarding agreements or partnerships.
*   **Sedes y Contacto:** Links providing location and contact details.
*   **¿Sabías qué?:** Links to informational Q&A pages.
*   **Formación Integral:** Information about integral education.
*   **Académica:** Academic information links.
*   **Artística:** Links related to artistic studies or programs.
*   **Científica:** Links related to scientific studies or programs.
*   **Deportiva:** Links related to sports or physical education.
*   **Humana:** Link related to humanistic studies or programs.
*   **Proyecto Educativo:** Information about the educational project.
*   **Propuesta Educativa:** Information regarding the educational proposal.
*   **Kindergarten:** Link for Kindergarten information.
*   **Educación Primaria:** Link for Primary education details.
*   **Educación Secundaria:** Link for Secondary education details.

## External Resources and Community Links

Links pointing to external systems, alumni, and community engagement.

*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to webmail services.
*   **Alumni:** Information for alumni.
*   **Comunidad:** Information about the school community.

## Navigation Control

*   **Toggle navigation:** Button used to show or hide the main navigation menu.
- stjohns.edu.ar/web/{token}/Kindergarten [Scouted, 54 components]
  Description: KINDER - Desde sala de uno a sala de cinco, las actividades del Kinder están basadas en el juego que es la principal fuente de aprendizaje de los niños. Con variadas actividades y propuestas para que ellos desarrollen su capacidad intelectual, física, emocional, lingüística y social en un ambiente e
  Components:
## Navigation and School Information

This section groups links related to the school's structure, history, contact, and institutional information.

### Main Navigation Links
*   **Toggle navigation:** Controls the visibility of the main navigation menu.
*   **El Colegio:** Link to information about the school itself.
*   **Institucional:** Link to institutional information.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Convenios:** Link regarding agreements and partnerships.
*   **Sedes y Contacto:** Link providing location details and contact information.
*   **¿Sabías qué?:** A general informational link.
*   **Formación Integral:** Information about the integral education program.
*   **Académica:** Academic information.
*   **Artística:** Information related to artistic studies.
*   **Científica:** Information related to scientific studies.
*   **Deportiva:** Information related to sports and physical education.
*   **Humana:** Information related to humanistic studies.

### School Identity and External Links
*   **St. John's School:** Link referring to the school name.
*   **Webmail:** Link to the webmail service.
*   **Moodle:** Link to the Moodle platform.
*   **Padres - Legajos:** Link for parents to access records.
*   **Convenios y Alianzas:** Link for agreements and alliances.

## Admissions and Program Links

This section groups links related to admissions procedures, educational levels, and specific program details.

### Admission Process Links
*   **Admisiones (Multiple instances):** Links related to the admission process.
*   **Iniciar proceso:** Link to start an application process.
*   **Entrevista:** Link related to scheduling or information about interviews.
*   **Calendario:** Link to view the school calendar.
*   **Descargar Folleto:** Link to download a brochure.

### Educational Levels and Programs
*   **Kinder:** Link related to Kindergarten programs.
*   **Primaria (Primer ciclo):** Link specifically for the Primary cycle.
*   **Educación Primaria:** Link to primary education information.
*   **Educación Secundaria:** Link to secondary education information.
*   **Kindergarten:** Link to Kindergarten details.

### Academic and Community Links
*   **Proyecto Educativo:** Information regarding the educational project.
*   **Propuesta Educativa:** Information regarding the educational proposal.
*   **Alumni:** Information for former students or alumni.
*   **Comunidad:** Information about the school community.

## Language Options
*   **Español:** Link to the Spanish language version of the page.
*   **English:** Link to the English language version of the page.

## Custom Controls
*   **Equipo de profesionales (Multiple instances):** A custom control element likely displaying information about the professional team.
- stjohns.edu.ar/web/{token}/Kindergarteneng [Scouted, 56 components]
  Description: KINDER - From two year olds through five year olds, activities in the kInderegarten are based on play, the main tool in the learning process of small chilren. Activities in our integrated curriculum are designed to stimulate the development of social, emotional, linguistic, intellectual and physical
  Components:
## Navigation and School Information

This section groups links related to school programs, admissions, and institutional details.

### Admissions and School Levels
*   **Admissions:** Links related to the admissions process, including general admission information and starting the application process.
*   **Kindergarten:** Links specifically about Kindergarten programs or applications.
*   **Primary School:** Links relating to primary education options.
*   **Secondary School:** Links relating to secondary education options.
*   **Primary (First cycle):** A link related to the first cycle of primary education.
*   **Secondary:** A link related to secondary level information.

### Academic and Program Details
*   **Academics:** Information regarding the school's academic offerings.
*   **Arts:** Information about the arts programs.
*   **Science:** Information about the science programs.
*   **Sports:** Information about sports activities.
*   **Social Skills:** Information about social skills development.
*   **Integral Formation:** Information regarding integral formation.
*   **Educational Project:** Information on educational projects available.
*   **Educational Proposal:** Information on educational proposals.

### Institutional and History
*   **The School:** General information about the school.
*   **Institutional:** Links related to the institution's structure or status.
*   **Our History:** Information detailing the school's history.
*   **Agreements:** Links regarding various agreements.
*   **Sites And Contacts:** Links providing site navigation and contact information.

### Alumni and Community
*   **Alumni:** Information for alumni.
*   **Community:** Information related to the school community.

## School Navigation and Contact

This section includes links for external resources, communication methods, and language options.

### External Resources and Communication
*   **Moodle:** A link to Moodle resources.
*   **Webmail:** A link to webmail services.
*   **Webmail (unlabeled):** An unlabeled link element.

### Action Links
*   **Work with us. Send CV:** A link prompting users to send a CV or express interest in working with the school.
*   **Padres - Legajos:** A link likely related to parents and official records.
*   **Interview:** A link to start an interview process.
*   **Calendar:** A link to view the school calendar.
*   **Download Brochure:** A link to download a brochure.

### Language Options
*   **EN:** Link for English language content.
*   **Español:** Link for Spanish language content.
*   **English:** Link for English language content (likely redundant or alternative).

## Interactive Elements

### Navigation Control
*   **Toggle navigation:** A button used to toggle the main navigation menu.

### Hidden Fields
*   Two hidden text fields are present on the page, without visible labels.

### Staff Information
*   Two custom controls labeled "Staff" are present, likely for staff directories or specific staff actions.
- stjohns.edu.ar/web/{token}/Primaria [Scouted, 54 components]
  Description: PRIMARIA - El enfoque con respecto al aprendizaje de las dos lenguas es comunicacional, privilegiando el contacto con diferentes tipos de textos y favoreciendo la posibilidad de expresarse correctamente en diferentes situaciones y por distintos medios. Con visitas semanales a la biblioteca nuestros 
  Components:
## Navigation and Main Links

This section includes primary navigation links for accessing different sections of the website:

*   **Admisiones:** Links related to admissions processes or information.
*   **Kinder:** Links related to kindergarten programs or information.
*   **Primaria:** Links related to primary education.
*   **Secundaria:** Links related to secondary education.
*   **Admisiones (repeated):** Additional links concerning admissions.
*   **Kinder (repeated):** Additional links concerning kindergarten.
*   **Primaria (Primer ciclo):** Link specifically for the primary cycle.
*   **Padres - Legajos:** Link likely leading to parent records or files.
*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to the school's webmail service.

## School and Institutional Information

These links provide details about the school, its history, structure, and partnerships:

*   **St. John's School:** Link referencing the school name.
*   **El Colegio:** Link related to the school structure or identity.
*   **Institucional:** Link providing institutional information.
*   **Nuestra Historia:** Link detailing the school's history.
*   **Convenios:** Links regarding agreements and partnerships.
*   **Sedes y Contacto:** Links for finding locations and contact information (repeated).
*   **¿Sabías qué?:** Links to general trivia or interesting facts.
*   **Formación Integral:** Link related to integral education.
*   **Académica:** Link providing academic details.
*   **Artística:** Link related to artistic programs.
*   **Científica:** Link related to scientific programs.
*   **Deportiva:** Link related to sports or physical education.
*   **Humana:** Link related to humanities.
*   **Proyecto Educativo:** Link detailing the educational project.
*   **Propuesta Educativa:** Link detailing the educational proposal.
*   **Kindergarten:** Link specifically for kindergarten.
*   **Educación Primaria:** Link for primary education details.
*   **Educación Secundaria:** Link for secondary education details.
*   **Alumni:** Link for alumni information.
*   **Comunidad:** Link related to the school community.
*   **Convenios y Alianzas:** Link for agreements and alliances.

## Application and Process Links

Links focused on application procedures, enrollment steps, and specific documents:

*   **Admisión:** Link for admission processes.
*   **Iniciar proceso:** Link to start an application process.
*   **Entrevista:** Link related to interviews.
*   **Calendario:** Link to the school calendar.
*   **Descargar Folleto:** Link to download brochures or flyers.
*   **ES:** Link potentially related to secondary education (e.g., ESO).
*   **Español:** Link for Spanish language resources.
*   **English:** Link for English language resources.

## Custom Content and External Links

These components feature custom content or links to external platforms:

*   **Equipo de profesionales (x2):** Components displaying information about the professional team.
*   **Moodle:** Link to the Moodle platform.
*   **Webmail:** Link to the webmail service.
*   **(no accessible label found on this element) (x2):** Unlabeled links present on the page.
- stjohns.edu.ar/web/{token}/Primary-School [Scouted, 56 components]
  Description: PRIMARY - Acquisition of both laguages is presented through a communicational globalized/whole language approach, presenting different types of texts to the children and stimulating their observation skills, their sense of comparison and their logical and critical thinking so that they may transfer 
  Components:
## Navigation and School Structure

This section contains links related to different educational levels and administrative areas of the school.

*   **Admissions:** Links for admissions processes, including general admissions, kindergarten admissions, primary school admissions, and secondary school admissions.
*   **School Levels:** Specific links for Primary (First cycle), Kindergarten, Primary School, and Secondary School.
*   **Administration & History:** Links providing information about the school's administration, history, agreements, sites, and contacts.
*   **Institutional Information:** Links covering general institutional details, such as "The School" and "Our History."

## Academic Programs and Offerings

This section includes links detailing the academic subjects and educational projects offered by the school.

*   **Curriculum Areas:** Links for specific subject areas including Arts, Science, Sports, and Social Skills.
*   **Program Details:** Links related to integral formation, academics, and educational proposals.
*   **Specific Cycles:** A link for "Primary (First cycle)."

## Admissions Process

Links guiding users through the application and inquiry process.

*   **Application Steps:** Links for starting the admission process, viewing interview information, and downloading brochures.
*   **Inquiry/Information:** Links related to hearing about the school ("Have you heard"), general admissions inquiries, and contacting the school.
*   **Contact & Records:** Links for accessing contact information, sites and contacts, parent records (Padres - Legajos), Moodle, and Webmail access.

## School Information and Alumni

Links providing context about the school and its community.

*   **School Identity:** A link to the main school name ("St. John's School").
*   **Community:** Links related to the community and alumni information.

## Language Options

Links allowing users to switch the language of the page.

*   English
*   Español

## Staff Information

Custom controls displaying staff-related information.

*   Staff listings (two instances).

***

*Note: There are several hidden or unlabelled text fields and links present on the page.*

## Digital Blueprint Summary: St. John's School Educational Portal

This section of the website serves as the educational information hub for St. John's School, providing detailed resources related to admissions, curriculum, institutional history, and community engagement. The pages are structured to guide prospective students, parents, alumni, and the wider community through various aspects of the school's offerings.

### Overview and Structure

The navigation structure is highly interconnected, focusing on core educational levels (Kindergarten, Primary, Secondary) and integral education components (Artistic, Scientific, Sports, Humanities). The site integrates institutional information with practical application links for admissions and communication platforms.

### Key Areas Covered

**1. Educational Levels and Curriculum:**
The routes are specifically tailored to provide information for different stages of schooling:
*   **Secondary Education (`/Secundaria`):** Focuses on the goals, autonomy, and academic excellence of secondary students (1st to 6th year).
*   **Sports/Physical Education (`/deportiva`):** Dedicated to the school's commitment to holistic development through sports training.

**2. Admissions and Enrollment:**
A consistent set of links facilitates the enrollment process, including information on:
*   Admissions processes and application procedures.
*   Information regarding different educational cycles (Kindergarten, Primary, Secondary).
*   Links for interviews, downloading brochures, and accessing school calendars.

**3. Institutional and Community Information:**
The portal provides comprehensive institutional context, linking academic content with school identity:
*   **History and Agreements:** Details on the school's history and formal agreements.
*   **School Identity:** Links to general information about the school (`El Colegio`, `Institucional`).
*   **Community Focus:** Resources for alumni, parent records, and community involvement.

**4. Academic Specializations:**
The site organizes educational content around specific streams of study, including:
*   Academic subjects (Arts, Science).
*   Programmatic areas (Deportiva, Humana).
*   Integral formation concepts (`Formación Integral`, `Proyecto Educativo`).

**5. Platform Integration:**
The portal integrates with internal learning and communication systems, providing access to:
*   Moodle learning platform.
*   Webmail services.
*   Language options (Spanish and English) for multilingual access.

## External Media Links

This section aggregates external links pointing to communication and video content. These pages do not constitute part of the primary website structure but serve as external resources linked from the application or site.

| Link | Description | Components |
| :--- | :--- | :--- |
| `wa.me/5491135427975` | Direct link to a WhatsApp contact. | 0 |
| `youtube.com/watch?v=RjK0ppPJ9iY` | Link to an external YouTube video. | 0 |
| `youtube.com/watch?v=fCcSxSysw2s` | Link to an external YouTube video. | 0 |
| `youtube.com/watch?v=qf6Uk2Tx2-I` | Link to an external YouTube video. | 0 |
| `youtube.com/watch?v=vVTbQGo37K8&t=1s` | Link to an external YouTube video. | 0 |

**Relationship:** These links provide access to external communication (WhatsApp) and multimedia content (YouTube).

## External Resources

This section documents external resources linked from the site.

| Route | Description | Components |
| :--- | :--- | :--- |
| `youtube.com/watch?v=xM-hXAaObzQ&t` | External video content link. | 0 |

## Navigation Graph

```mermaid
flowchart LR
```
