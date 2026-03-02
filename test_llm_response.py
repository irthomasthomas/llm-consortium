import llm
# Use an Echo model or whatever is safe/free
model = llm.get_model("gpt-4o-mini") # Just testing instantiation or we can use a mock
print(dir(model.prompt("test")))
