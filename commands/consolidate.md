Run memory consolidation for the current project.
Organizes facts into clusters, assigns knowledge tiers, and detects contradictions.
NEVER deletes anything — only organizes.

Steps:
1. Run the consolidation script:
   python ~/.memoriq/mcp-server/tools/consolidate.py

2. Show the user the consolidation report (clusters, tiers, contradictions).

3. If contradictions were detected, search for them:
   memory_search("contradictions") and show the user which facts may need review.

4. Update session bridge with consolidation results.
