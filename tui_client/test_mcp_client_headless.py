import sys
import os
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path to find mcp_server if needed
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

async def run_agent_test(user_query: str):
    print(f"\n--- Starting Agent Test with Query: '{user_query}' ---")
    
    # 1. Setup MCP Connection Parameters
    server_script = os.path.join(os.path.dirname(__file__), '..', 'mcp_server', 'server.py')
    python_exe = sys.executable 
    
    print(f"[Setup] Server Script: {server_script}")
    
    server_params = StdioServerParameters(
        command=python_exe, 
        args=[server_script], 
        env=os.environ.copy()
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                print("[MCP] Connected to server.")
                await session.initialize()
                
                # 2. Discover Tools
                mcp_tools_list = await session.list_tools()
                print(f"[MCP] Discovered {len(mcp_tools_list.tools)} tools: {[t.name for t in mcp_tools_list.tools]}")

                # 3. Convert to LangChain Tools
                langchain_tools = []
                for t in mcp_tools_list.tools:
                    @tool(t.name)
                    def dynamic_tool(**kwargs):
                        """Dynamic MCP Tool"""
                        pass
                    
                    dynamic_tool.name = t.name
                    dynamic_tool.description = t.description or "No description"
                    langchain_tools.append(dynamic_tool)

                # 4. Initialize LLM
                llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
                llm_with_tools = llm.bind_tools(langchain_tools)

                # 5. Run Agent
                messages = [HumanMessage(content=user_query)]
                print("[Agent] Thinking...")
                ai_msg = await llm_with_tools.ainvoke(messages)
                messages.append(ai_msg)

                # 6. Handle Tool Calls
                if ai_msg.tool_calls:
                    for tool_call in ai_msg.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        
                        print(f"[Agent] DECISION: Call tool '{tool_name}' with args: {tool_args}")
                        
                        # Execute via MCP
                        result = await session.call_tool(tool_name, arguments=tool_args)
                        
                        # Parse output
                        tool_output = ""
                        if result.content:
                            for c in result.content:
                                if c.type == "text": tool_output += c.text
                        
                        print(f"[MCP] Tool Output: {tool_output[:200]}...") # Truncate for display
                        messages.append(ToolMessage(content=tool_output, tool_call_id=tool_call["id"]))

                    # 7. Final Response
                    final_response = await llm_with_tools.ainvoke(messages)
                    print(f"\n[Agent] FINAL RESPONSE:\n{final_response.content}")
                else:
                    print(f"\n[Agent] FINAL RESPONSE (No tools used):\n{ai_msg.content}")

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Test query
    query = "Find all PDF documents related to invoices"
    if len(sys.argv) > 1:
        query = sys.argv[1]
        
    asyncio.run(run_agent_test(query))
