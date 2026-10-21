# Daily Dispatch – design document

Diagrams are in `dailydispatch_design.drawio` (open at app.diagrams.net or in the
draw.io desktop app). It has five pages: **ERD**, **UseCases**, **PageFlow**,
**Wireframes** and **ApprovalFlow**.

## 1. Functional requirements

| ID | Requirement |
|---|---|
| FR1 | Users register and log in. Registration offers all three roles: Reader, Editor and Journalist. |
| FR2 | Each user has one role (Reader, Editor, Journalist) and is placed in the matching group, which carries the permissions. |
| FR3 | Journalists create, view, update and delete their own articles, independent or under a publisher they write for. |
| FR4 | An article with no publisher is independent: it starts as a draft and its author publishes it with a Publish button. An article under a publisher stays pending until an editor approves it, and has no Publish button. The server enforces both rules in the web views, the API and the model. |
| FR5 | Editors see a review queue, approve articles, and can update or delete any article. |
| FR6 | On first approval, subscribers of the article's journalist or publisher are emailed the article. |
| FR7 | On first approval, the article is POSTed to our own `/api/approved/` endpoint, which logs it. |
| FR8 | Readers subscribe to publishers and to individual journalists. |
| FR9 | Journalists create newsletters, curated collections of approved articles. Editors can update and delete newsletters. Everyone can view them. |
| FR10 | Publishers have several editors and several journalists. |
| FR11 | A token-authenticated REST API provides: list approved articles, subscribed articles, retrieve, create (journalists), update and delete (editors and journalists), approve (editors), plus newsletters, publishers and the current user. |
| FR12 | Role rules apply to the API: only journalists create, only editors approve, readers can only view. |
| FR13 | Journalists have no reader subscriptions, and readers have no authored content. |
| FR14 | Email addresses are unique (case-insensitive), so subscriptions and notifications reach one account. |
| FR15 | A new user is logged in automatically after registering. |
| FR16 | Editors create and edit publishers and assign editors and journalists to them. |
| FR17 | Journalists have a My articles page listing drafts, pending and published articles, with Edit, Delete and (for independent drafts) Publish buttons. |
| FR18 | Only published articles can be added to a newsletter, in the form, the API and the model. |

## 2. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR1 | **Security:** passwords are hashed, pages and endpoints require login or a token, and access is enforced on the server by group permissions and role checks, not just by hiding links. The internal log endpoint needs a shared secret. |
| NFR2 | **Reliability:** a failing mail server or log endpoint must not stop an approval. Failures are logged. |
| NFR3 | **Data integrity:** the database is normalised to 3NF, with foreign keys and unique constraints. Subscribers never receive duplicate emails. |
| NFR4 | **Maintainability:** PEP 8, descriptive names, small modules (models, services, signals, views, serializers, permissions) and comments explaining why. |
| NFR5 | **Testability:** automated unit tests cover every role, both successful and failed requests, and mock email and HTTP calls. |
| NFR6 | **Usability:** a responsive Bootstrap layout, navigation that shows only the links a role may use, clear success and error messages, and paginated lists. |
| NFR7 | **Portability:** runs on MariaDB through Django's MySQL backend. Connection details come from environment variables. |
| NFR8 | **Performance:** list views use `select_related`, pagination and distinct subscriber queries. |

## 3. UI/UX plan

See the **PageFlow** and **Wireframes** pages.

- One shared layout with a dark navigation bar. The links shown depend on the
  user's permissions: Write article and New newsletter for journalists, Review
  queue for editors, My subscriptions for readers.
- Article list as cards (title, author, publisher or "Independent", date,
  40-word preview). Unapproved articles are only visible to their author and
  to editors, and are marked "Awaiting approval".
- The editor review queue puts Approve, Edit and Reject on every card, so an
  article can be handled without opening it.
- Subscriptions are two checkbox lists (publishers, journalists) with one Save
  button.
- Feedback uses Bootstrap alerts. Deleting always goes through a confirmation
  page.

## 4. Database normalisation

See the **ERD** page.

- **1NF:** every column holds a single value. Lists such as subscriptions,
  publisher staff and newsletter contents are separate rows in junction
  tables, not comma-separated text.
- **2NF:** each junction table (PublisherEditor, PublisherJournalist,
  ReaderPublisherSub, ReaderJournalistSub, NewsletterArticle, UserGroup) has
  only the two foreign keys it joins, so nothing depends on part of a key.
- **3NF:** an article stores `author_id` and `publisher_id`, not the author's
  or publisher's details. The names live in CustomUser and Publisher. Role
  permissions live in `auth_Group`, not repeated per user.
- **Nullable foreign keys:** `Article.publisher_id` is null for independent
  articles. `Article.approved_by_id` is null until approval.

## 5. Approval design decision

Independent articles are published by their author (the Publish button or
`POST /api/articles/<id>/publish/`); publisher articles are approved by an
editor. Both end in the same step: `approved` becomes true, and the signal
below runs.

Option 1 (signals) is used. A `post_save` receiver on Article reacts when
`approved` becomes true, and an `approval_notified` flag makes sure emails and
the log POST happen only once. See the **ApprovalFlow** page. The signal keeps
the web view and the REST API approval paths identical.

## 6. Role permissions

| Permission | Reader | Editor | Journalist |
|---|---|---|---|
| View articles and newsletters | yes | yes | yes |
| Create articles | – | – | yes |
| Create newsletters | – | – | yes |
| Update articles and newsletters | – | any | own |
| Delete articles and newsletters | – | any | own |
| Approve articles | – | yes | – |
| Subscribe | yes | – | – |
