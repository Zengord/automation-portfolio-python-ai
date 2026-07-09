# n8n Workflow Idea

This document describes how the local Python utilities from this repository can be connected to an n8n workflow.

## Website Audit Workflow

1. **Webhook Trigger**

   Receives a project archive, a folder path on a server, or metadata about the site that should be checked.

2. **Execute Command**

   Runs the Python website auditor:

   ```bash
   python src/website_auditor/check_links.py
   ```

3. **Code Node**

   Normalizes the result into structured fields:

   - total issues;
   - broken links;
   - broken images;
   - missing metadata;
   - warnings;
   - report file path.

4. **LLM / AI Agent Node**

   Converts the technical report into a short action list for a manager, developer, or content editor.

5. **Google Sheets / Database**

   Stores audit history and issue counts.

6. **Telegram / Slack / Email**

   Sends a short notification with the most important findings.

## Why This Workflow Is Useful

- The input and output are clear.
- The Python script handles the technical validation.
- n8n handles orchestration, scheduling, routing, and notifications.
- The AI step is used for summarization, while the actual checks remain deterministic.
