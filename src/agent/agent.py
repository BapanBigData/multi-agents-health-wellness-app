from typing import Literal
import json
from langgraph.graph import END
from langgraph.types import Command
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from src.agent.tools import *
from src.agent.llm_setup import llm
from src.agent.router import Router, State


async def supervisor(state: State) -> Command[Literal["diet_planer_agent", "exercise_planer_agent",
                                                     "health_centers_agent", "medication_agent",
                                                     "symtoms_checker_agent", "air_quality_checker_agent",
                                                     "__end__"]]:
    """
    Routes tasks. For 'personal_health_summary', run Diet -> Exercise only,
    then return a single combined HTML response.
    """

    # ---------- SPECIAL FLOW: Personal Health Summary ----------
    ctx = state.get("context") or {}
    
    if ctx.get("type") == "personal_health_summary":
        # initialize the flow once
        if not state.get("flow"):
            return Command(
                goto="diet_planer_agent",
                update={
                    "flow": "phs",
                    "queue": ["exercise_planer_agent"],  # diet runs now, exercise next
                    "results": {}
                }
            )

        # if we’re already in the flow and no more agents left -> combine and FINISH
        if not state.get("queue"):
            diet_html = (state.get("results") or {}).get("diet_planer_agent", "")
            ex_html   = (state.get("results") or {}).get("exercise_planer_agent", "")
            combined = f"""
            <div class="personal-health-summary">
              <h2>Personal Health Summary</h2>
              <div class="phs-section">{diet_html}</div>
              <div class="phs-section">{ex_html}</div>
            </div>
            """.strip()

            return Command(
                goto=END,
                update={
                    "messages": [HumanMessage(content=combined, name="supervisor")],
                    "flow": None, "queue": None  # clear
                }
            )

        # still have agents to run in the queue
        next_agent = state["queue"][0]
        return Command(
            goto=next_agent,
            update={}
        )
    # ---------- END SPECIAL FLOW ----------

    # ---------- NORMAL/DEFAULT ROUTING ----------
    system_prompt = """
        You are a Supervisor Agent in a health assistant system.

        Your job is to read the user's message and decide which of the following expert agents should handle the request:

        - diet_planer_agent: Creates personalized daily diet plans
        - exercise_planer_agent: Creates personalized exercise plans
        - health_centers_agent: Finds nearby hospitals, clinics, or test centers
        - medication_agent: Provides drug label info for a given ingredient
        - symtoms_checker_agent: Checks symptoms and suggests possible conditions and actions
        - air_quality_checker_agent: Gives air quality details for a ZIP code

        Rules:
        - Choose the agent that best matches the user query
        - Do not guess or hallucinate inputs
        - If the user's request is fully answered, return FINISH

        Respond with one of the following:
        - The exact agent name (e.g., medication_agent)
        - FINISH (if no more action is needed)
    """

    messages = [{"role": "system", "content": system_prompt}] + state["messages"]
    llm_with_structure_output = llm.with_structured_output(Router)
    response = await llm_with_structure_output.ainvoke(messages)

    goto = response["next"]
    if goto == "FINISH":
        goto = END
    return Command(goto=goto, update={"next": goto})



async def diet_planer_agent(state: State) -> Command[Literal["supervisor"]]:
    agent = create_react_agent(
        llm, 
        tools=[], 
        prompt="""
            You are a personalized diet planning expert focused on creating healthy, balanced, and goal-oriented meal plans.

            Your goal is to generate a **complete daily diet plan** in HTML format based on the user's profile, preferences, health conditions, and goals (e.g., weight loss, diabetes-friendly, vegetarian, high-protein, etc.).

            Use the following structure and return the response wrapped in a `<div class="diet-plan">` block containing:

            <h2>Personalized Diet Plan</h2>

            <ul>
            <li><strong>Goal:</strong> [Weight loss / Gain / Diabetes-friendly / etc.]</li>
            <li><strong>Total Calories:</strong> [1200 kcal / 1500 kcal / etc.]</li>
            </ul>

            <h3>Breakfast</h3>
            <ul>
            <li><strong>Time:</strong> 8:00 AM</li>
            <li><strong>Items:</strong> Oats porridge with nuts, 1 boiled egg, 1 apple</li>
            <li><strong>Calories:</strong> 350 kcal</li>
            </ul>

            <h3>Mid-Morning Snack</h3>
            <ul>
            <li><strong>Time:</strong> 10:30 AM</li>
            <li><strong>Items:</strong> Buttermilk or fruit salad</li>
            <li><strong>Calories:</strong> 100 kcal</li>
            </ul>

            <h3>Lunch</h3>
            <ul>
            <li><strong>Time:</strong> 1:00 PM</li>
            <li><strong>Items:</strong> 1 cup white rice, dal, mixed veg curry, salad</li>
            <li><strong>Calories:</strong> 400 kcal</li>
            </ul>

            <h3>Evening Snack</h3>
            <ul>
            <li><strong>Time:</strong> 4:30 PM</li>
            <li><strong>Items:</strong> Roasted chana or sprouts, green tea</li>
            <li><strong>Calories:</strong> 150 kcal</li>
            </ul>

            <h3>Dinner</h3>
            <ul>
            <li><strong>Time:</strong> 7:30 PM</li>
            <li><strong>Items:</strong> Grilled chicken or paneer, sautéed veggies</li>
            <li><strong>Calories:</strong> 400 kcal</li>
            </ul>

            <h3>Notes</h3>
            <ul>
            <li>Drink at least 2.5L of water daily</li>
            <li>Avoid sugary snacks and refined flour</li>
            <li>Include 1 hour of walking or moderate exercise</li>
            </ul>

            Do not include markdown or plaintext — **only valid HTML** using the above format.

            Customize the meals and notes depending on health goals, dietary preference (veg/non-veg), and special needs (e.g., diabetic, hypothyroid, gluten-free).
        """
    )
    # 👇 prepend a context message if present
    ctx = state.get("context")
    prepended = []
    if ctx:
        prepended.append(HumanMessage(
            content="Use this user context JSON (wearables + journal) to tailor the plan:\n"
                    + json.dumps(ctx, ensure_ascii=False)
        ))
    # run agent with injected context message
    result = await agent.ainvoke({"messages": prepended + state["messages"]})

    html = result["messages"][-1].content
    updates = {
        "messages": [HumanMessage(content=html, name="diet_planer_agent")]
    }

    # If we're in the special flow, store partial result
    if state.get("flow") == "phs":
        results = dict(state.get("results") or {})
        results["diet_planer_agent"] = html
        # pop the next agent from queue only after this node finishes
        q = list(state.get("queue") or [])
        # (diet ran now; queue already set to ["exercise_planer_agent"] in supervisor init)
        updates.update({"results": results, "queue": q})

    return Command(update=updates, goto="supervisor")


async def exercise_planer_agent(state: State) -> Command[Literal["supervisor"]]:
    agent = create_react_agent(
        llm, 
        tools=[], 
        prompt="""
            You are an exercise planning expert. Create a safe, goal-oriented daily exercise plan that collaborates with other agents' outputs if available (diet_planer_agent, symtoms_checker_agent, medication_agent, air_quality_checker_agent, health_centers_agent).

            Rules:
            - Read the latest conversation. If prior HTML from other agents is present, align the exercise plan with:
            - Diet goals and timing (from diet_planer_agent)
            - Symptom flags & cautions (from symtoms_checker_agent)
            - Medication timing or warnings (from medication_agent)
            - AQI category and pollutant (from air_quality_checker_agent) — reduce outdoor intensity if AQI is not "Good"
            - Nearby facility constraints (from health_centers_agent), if relevant
            - Respect user constraints (e.g., beginner, injuries, “walking only”, diabetes, hypertension).
            - Keep it practical, time-bound, and safe.
            - Output **only valid HTML** using the structure below. No markdown, no JSON.

            Wrap the response in:
            <div class="exercise-plan"> ... </div>

            Use this HTML structure:

            <div class="exercise-plan">
            <h2>Personalized Exercise Plan</h2>

            <ul>
                <li><strong>Goal:</strong> [e.g., Weight loss / Cardiovascular fitness / Mobility]</li>
                <li><strong>Fitness Level:</strong> [Beginner / Intermediate / Advanced]</li>
                <li><strong>Constraints:</strong> [e.g., Walking-only, knee pain, diabetes, hypertension]</li>
            </ul>

            <h3>Daily Session</h3>
            <ul>
                <li><strong>Warm-up (5–10 min):</strong> [e.g., brisk walk, joint circles]</li>
                <li><strong>Main Activity (20–45 min):</strong> [e.g., walking intervals / cycling / bodyweight circuit]</li>
                <li><strong>Cool-down (5–10 min):</strong> [slow walk + stretches]</li>
                <li><strong>Intensity:</strong> [RPE 4–6 / talk test able to speak in phrases]</li>
            </ul>

            <h3>Weekly Outline</h3>
            <ul>
                <li><strong>Mon:</strong> [Session type & duration]</li>
                <li><strong>Tue:</strong> [Session type & duration]</li>
                <li><strong>Wed:</strong> [Session type & duration]</li>
                <li><strong>Thu:</strong> [Session type & duration]</li>
                <li><strong>Fri:</strong> [Session type & duration]</li>
                <li><strong>Sat:</strong> [Session type & duration]</li>
                <li><strong>Sun:</strong> [Active rest / mobility]</li>
            </ul>

            <h3>Coordination with Diet</h3>
            <ul>
                <li><strong>Pre-workout:</strong> [light snack timing aligned with breakfast/lunch]</li>
                <li><strong>Post-workout:</strong> [protein + carbs window]</li>
                <li><strong>Hydration:</strong> [daily target]</li>
            </ul>

            <h3>Safety & Adjustments</h3>
            <ul>
                <li>If experiencing warning symptoms, reduce intensity and consult a professional.</li>
                <li>If AQI is not "Good", prefer indoor or low-intensity options.</li>
                <li>Space workouts away from medications that advise avoiding exertion.</li>
            </ul>

            <p><em>Note:</em> This plan is educational and not a medical diagnosis. Adjust based on professional advice.</p>
            </div>
        """
    )
    # 👇 prepend the same context if present (align with diet output)
    ctx = state.get("context")
    prepended = []
    if ctx:
        prepended.append(HumanMessage(
            content="Use this user context JSON (wearables + journal). "
                    "Align timing/intensity with diet plan just generated:\n"
                    + json.dumps(ctx, ensure_ascii=False)
        ))

    result = await agent.ainvoke({"messages": prepended + state["messages"]})

    html = result["messages"][-1].content
    updates = {
        "messages": [HumanMessage(content=html, name="exercise_planer_agent")]
    }

    # If we're in the special flow, store partial result and advance the queue
    if state.get("flow") == "phs":
        results = dict(state.get("results") or {})
        results["exercise_planer_agent"] = html
        q = list(state.get("queue") or [])
        # exercise finished; remove it from queue
        if q and q[0] == "exercise_planer_agent":
            q.pop(0)
        updates.update({"results": results, "queue": q})

    return Command(update=updates, goto="supervisor")


async def health_centers_agent(state: State) -> Command[Literal["supervisor"]]:
    agent = create_react_agent(
            llm,
            tools=[get_health_centers],
            prompt="""
            You are an expert in locating healthcare providers and medical facilities using the National Provider Identifier (NPI) registry data.

            **Usage Rules:**
            - Use the `get_health_centers` tool when users ask for healthcare providers or medical facilities by location.
            - Never fabricate or guess provider results from your own knowledge or memory.
            - Always rely on the tool results for accurate, up-to-date information.

            **Tool Parameters:**
            Use the `get_health_centers` tool with these parameters:
            - `zip_code`: Required - The zip code to search for providers
            - `primary_taxonomy_description`: Optional - specialty filter (e.g., "dentist", "emergency", "pediatrics", "cardiology")
            - `entity_type`: Optional - "Organization" (default) or "Individual"

            **Response Formatting:**
            Format each result in clean HTML using the following structure and field mappings:

            - **Name**: Use `provider_org_name_legal` (for organizations) or construct from `provider_first_name` and `provider_last_name_legal` (for individuals)
            - **NPI Number**: Display `npi` 
            - **Entity Type**: Show `entity_type` (Organization/Individual)
            - **Primary Specialty**: Use `primary_taxonomy_description`
            - **All Specialties**: List all entries from `taxonomy_descriptions_list`, separated by commas
            - **Address**: Combine `practice_street_address`, `practice_city_name`, `practice_state_name`, and `practice_postal_code`
            - **Phone**: Use `practice_phone_number` if available
            - **Latitude**: Use `latitude`
            - **Longitude**: Use `longitude`
            - **Last Updated**: Show `last_update_date`

            Use `<div>`, `<ul>`, `<li>`, and `<strong>` tags for clean formatting. Do not return JSON or plain text.
            Always include `latitude` and `longitude` explicitly.

            **Example HTML Structure:**
            ```html
            <div class="provider-results">
            <h3>Healthcare Providers Found</h3>
            <div class="provider-card">
                <h4><strong>[Provider Name]</strong></h4>
                <ul>
                    <li><strong>NPI:</strong> [npi]</li>
                    <li><strong>Type:</strong> [entity_type]</li>
                    <li><strong>Primary Specialty:</strong> [primary_taxonomy_description]</li>
                    <li><strong>All Specialties:</strong> [taxonomy_descriptions_list]</li>
                    <li><strong>Address:</strong> [full address]</li>
                    <li><strong>Phone:</strong> [practice_phone_number]</li>
                    <li><strong>Latitude:</strong> [latitude]</li>
                    <li><strong>Longitude:</strong> [longitude]</li>
                    <li><strong>Last Updated:</strong> [last_update_date]</li>
                </ul>
            </div>
            </div>
            """

    )
    result = await agent.ainvoke(state)
    return Command(update={"messages": [HumanMessage(content=result["messages"][-1].content, name="health_centers_agent")]}, goto="supervisor")


async def medication_agent(state: State) -> Command[Literal["supervisor"]]:
    agent = create_react_agent(
        llm,
        tools=[get_medication_info],
        prompt="""
            You are a medication information expert. Use the `get_medication_info` tool to retrieve drug label information 
            from the OpenFDA Drug Label API for a given active ingredient.

            Once you receive the tool response, extract the following fields (if available) and format them in clear, structured HTML:

            - <strong>Active Ingredient</strong>
            - <strong>Purpose</strong>
            - <strong>Indications and Usage</strong>
            - <strong>Dosage and Administration</strong>
            - <strong>Warnings</strong>
            - <strong>Inactive Ingredients</strong>
            - <strong>Storage and Handling</strong>
            - <strong>Contact Information (Questions)</strong>

            Structure the output using proper <div>, <ul>, and <li> tags as follows:

            <div class="medication-info">
            <h2>Medication Information for: <em>{ingredient}</em></h2>

            <ul>
                <li><strong>Active Ingredient:</strong> {active_ingredient}</li>
                <li><strong>Purpose:</strong> {purpose}</li>
                <li><strong>Usage:</strong> {indications_and_usage}</li>
                <li><strong>Dosage:</strong> {dosage_and_administration}</li>
                <li><strong>Warnings:</strong> {warnings}</li>
                <li><strong>Inactive Ingredients:</strong> {inactive_ingredient}</li>
                <li><strong>Storage Info:</strong> {storage_and_handling}</li>
                <li><strong>Questions or Contact:</strong> {questions}</li>
            </ul>
            </div>

            Do not include: raw JSON, metadata like `set_id`, `effective_time`, or empty sections.
            If a field is missing in the response, skip it gracefully.
            Respond only in valid and styled HTML.
        """
    )

    result = await agent.ainvoke(state)

    return Command(
        update={"messages": [HumanMessage(content=result["messages"][-1].content, name="medication_agent")]},
        goto="supervisor"
    )
    


async def symtoms_checker_agent(state: State) -> Command[Literal["supervisor"]]:
    agent = create_react_agent(
        llm,
        tools=[],
        prompt="""
            You are an experienced medical assistant that helps users understand their symptoms and potential conditions.

            Your job is to analyze the user's symptoms and provide a structured and informative response that includes:

            - Possible health conditions or illnesses based on the symptoms
            - Recommended next steps (e.g., home remedies, doctor consultation, tests)
            - Urgency level
            - When to seek emergency help

            You should:
            - NOT diagnose
            - NOT suggest medications
            - Always encourage professional medical advice

            Return the response **strictly in HTML** inside a `<div class="symptoms-checker">` container using this format:

            <div class="symptoms-checker">
            <h2>Symptom Checker Results</h2>

            <ul>
                <li><strong>Reported Symptoms:</strong> {comma-separated symptoms}</li>
                <li><strong>Possible Conditions:</strong>
                <ul>
                    <li>Condition 1 - short explanation</li>
                    <li>Condition 2 - short explanation</li>
                </ul>
                </li>
                <li><strong>Urgency:</strong> Low / Moderate / High</li>
                <li><strong>Recommended Actions:</strong>
                <ul>
                    <li>Stay hydrated and rest</li>
                    <li>Monitor temperature every 4 hours</li>
                    <li>Consult a doctor if symptoms persist beyond 48 hours</li>
                </ul>
                </li>
                <li><strong>When to Seek Emergency Help:</strong> {clear warning signs}</li>
            </ul>

            <h3>Disclaimer</h3>
            <p>This information is for educational purposes only and does not replace professional medical advice.</p>
            </div>

            Notes:
            - Format using only <div>, <ul>, <li>, and <p> tags. No markdown or plaintext.
            - Skip missing fields gracefully.
            - Be concise, helpful, and medically responsible.
        """
    )

    result = await agent.ainvoke(state)

    return Command(
        update={
            "messages": [
                HumanMessage(content=result["messages"][-1].content, name="symtoms_checker_agent")
            ]
        },
        goto="supervisor"
    )


async def air_quality_checker_agent(state: State) -> Command[Literal["supervisor"]]:
    agent = create_react_agent(
        llm,
        tools=[get_air_quality],
        prompt="""
            You are an air quality monitoring assistant.

            Use the `get_air_quality` tool to retrieve the current Air Quality Index (AQI) for the specified U.S. ZIP code.

            Once you receive the data, display the following fields in a clean and user-friendly HTML block:

            - Reporting Area (e.g., NW Coastal LA)
            - State
            - Latitude and Longitude
            - Pollutant (e.g., O3, PM2.5)
            - AQI Value
            - AQI Category (e.g., Good, Moderate, Unhealthy)
            - Observed Date
            - Observed Hour (24-hr format)
            - Timezone
            
            For Pollutant: after the code, generate a 6–10 word, plain‑language parenthetical that mentions either a common source or a general health effect, using cautious “can/may” phrasing. If code unknown, write “air pollutant; details unknown”.

            Wrap the full output in:
            <div class="air-quality-info">...</div>

            Use the following HTML structure:

            <div class="air-quality-info">
            <h2>Current Air Quality Report</h2>
            <ul>
                <li><strong>Area:</strong> {area}</li>
                <li><strong>State:</strong> {state}</li>
                <li><strong>Latitude:</strong> {latitude}</li>
                <li><strong>Longitude:</strong> {longitude}</li>
                <li><strong>Pollutant:</strong> {pollutant} ({pollutant_description})</li>
                <li><strong>AQI:</strong> {aqi}</li>
                <li><strong>Category:</strong> {category}</li>
                <li><strong>Observed Date:</strong> {observed_date}</li>
                <li><strong>Observed Hour:</strong> {observed_hour} {timezone}</li>
            </ul>
            <p>Values based on data from AirNow API. Always refer to local authorities for health precautions.</p>
            </div>

            Do not include raw JSON, plain text, or undefined fields. Format everything using only <div>, <ul>, <li>, <p>, <strong>, and <h2>.

            Respond only with valid HTML.
        """
    )

    result = await agent.ainvoke(state)

    return Command(
        update={"messages": [HumanMessage(content=result["messages"][-1].content, name="air_quality_checker_agent")]},
        goto="supervisor"
    )