import llm
try:
    model = llm.get_model('openrouter/moonshotai/kimi-k2.5')
    if model.needs_key:
        model.key = llm.get_key('', model.needs_key, model.key_env_var)
    response = model.prompt("Return 'hello'", stream=False)
    print("Response text:", repr(response.text()))
except Exception as e:
    import traceback
    traceback.print_exc()
