# 🧠 DOM Mapper Skill Mind-Map: AUSTRAL University Portal Structure

This mind-map organizes the observed URLs and content into a functional, hierarchical structure, mapping out the key areas of the website and how they relate to different locations (`Sede`).

***

## 🌐 Root: austral.edu.ar (University Main Portal)

### 🎓 I. Academia & Education
*   **Posgrados (Postgraduate Studies)**
    *   `ro/posgrados` (General Index)
    *   Filter: Sede CABA (`?sede=caba`)
    *   Filter: Sede Pilar (`?sede=pilar`)
*   **Profesores (Staff Directory)**
    *   Directory Root: `ro/profesores/?sede=rosario` (Rosario specific)
    *   *Specific Profiles:* Sebastián Balsells (Includes location filters for CABA)
*   **Talleres y Cursos (Workshops & Courses)**
    *   Taller de Abogacía (Law Workshop)
        *   Filter: Sede CABA (`?sede=caba`)
    *   Taller de Anatomía (Anatomy Workshop)
        *   Filter: Sede CABA (`?sede=caba`)
    *   Triatlón Matemático (Math Triathlon)
        *   Filter: Sede CABA (`?sede=caba`)

### 📰 II. Información y Actualidad (News & Media)
*   **Novedades (General News)**
    *   Index: `ro/novedades`
    *   Filter: Sede CABA (`?sede=caba`)
    *   Filter: Sede Rosario (`?sede=rosario`)
*   **Prensa (Press Room / Media Center)**
    *   Index: `sala-de-prensa`
    *   Filter: Sede CABA (`?sede=caba`)
    *   Filter: Sede Pilar (`?sede=pilar`)
*   **Artículos Destacados (Featured Articles/Blog Feed)**
    *   Un estudio revela las razones por las que... (Article on Parenthood)
        *   View: General Article Page
        *   Filter: Sede CABA (`/?sede=caba`)
        *   Filter: Sede Pilar (`/?sede=pilar`)
    *   Unicef presentó una guía para investigar delitos digitales... (Article on Digital Crime)
        *   View: General Article Page
        *   Filter: Sede CABA (`/?sede=caba`)
        *   Filter: Sede Pilar (`/?sede=pilar`)

### 🧑‍🎓 III. Estudiante y Vida Universitaria (Student Life & Resources)
*   **Vida Universitaria (University Life)**
    *   Index Root: `vidauniversitaria`
    *   Filter: Sede CABA (`?sede=caba`)
    *   Filter: Sede Pilar (`?sede=pilar`)
    *   Sub-Section: Cómo Participar (How to Participate/Get Involved)
        *   Filter: Sede CABA (`/?sede=caba`)
        *   Filter: Sede Pilar (`/?sede=pilar`)
*   **Becas y Ayuda Universitaria (Scholarships & Aid)**
    *   Resource: Ver Reglamento General (PDF Link - Specific file versioning observed)
*   **Material Promocional/General Resources**
    *   Folleto General 2025 (Brochure PDF Link)

### 🌱 IV. Institucional y Soporte (Institutional & Support)
*   **Sostenibilidad (Sustainability)**
    *   Index Root: `sostenibilidad`
    *   Filter: Sede CABA (`?sede=caba`)
    *   Filter: Sede Pilar (`?sede=pilar`)
*   **Ubicación y Sedes Principales (Location Markers)**
    *   Sede CABA Button/Link (`/sede-caba`)

***

### 🛠️ Functional Relationships Summary

| Relationship Type | Description | Examples of Links |
| :--- | :--- | :--- |
| **Topic Filtering** | Core topics (Novedades, Posgrado) that must be viewed through a specific physical location filter. | `/rosario/novedades` $\rightarrow$ `?sede=caba` / `?sede=rosario` |
| **Sequential Content** | Articles or news items that are replicated across different local versions of the site. | Article X (General) $\rightarrow$ ?sede=caba AND ?sede=pilar |
| **Cross-Cutting Resources** | Documents or resources (PDFs, guides) that apply universally regardless of location. | *Reglamento General* PDF; *Folleto* PDF |
| **Primary Navigation** | High-level sections acting as hubs for related content and services. | Vida Universitaria, Prensa, Sostenibilidad |