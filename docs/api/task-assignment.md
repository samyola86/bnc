# Newsroom task assignments

`newsroom_tasks` persists title, description, assignee, creator, optional story ID, priority (LOW/MEDIUM/HIGH/URGENT), timezone-aware due date, status, creation/update/completion times and feedback. Assignments are independent of story ownership and contributor bylines.

Superadmins create/edit/reassign tasks, supply feedback, view all workloads and reopen completed tasks. Assignees must be active Editors or Content Writers. A story-linked assignment explicitly grants its assignee access to that story. Reassignment removes this grant from the former assignee, unless they own the story or have another assignment. Historical authorship never changes.

Editors and Writers use My Tasks to view their own work and history. Other users cannot retrieve or mutate a restricted task. Normal transitions are TO_DO → IN_PROGRESS → IN_REVIEW → COMPLETED; users may return an IN_REVIEW task to IN_PROGRESS. Story-linked completion requires APPROVED/READY. Approval automatically completes linked tasks already IN_REVIEW. Standalone assignments can complete after progress. Superadmins may reopen/reassign work; completed timestamps clear on reopening. Completion never implies platform publication.

All routes are authenticated under `/api/v1`:

- `GET /tasks` lists own tasks. `?all_tasks=true` returns all tasks only for Superadmins.
- `POST /tasks` and `PATCH /tasks/{id}` are Superadmin-only assignment operations.
- `POST /tasks/{id}/status` accepts the target `status` and enforces actor/transition rules.
- `GET /tasks/{id}/history` returns retained assignment/status/feedback audit events.

The current list limit is 200. Due dates are stored in UTC and displayed/entered in Asia/Dhaka. Task history records old/new assignees for reassignment. There are no notification emails or automatic deadlines in this phase.
