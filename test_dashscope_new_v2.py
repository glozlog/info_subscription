import dashscope
import os

# Set API Key (New Key provided by user)
api_key = "sk-cf39b266d6534e0da009dd11ed632b4f"
dashscope.api_key = api_key

def test_model(model_name):
    print(f"\n--- Testing Model: {model_name} ---")
    try:
        messages = [{'role': 'system', 'content': 'You are a helpful assistant.'},
                    {'role': 'user', 'content': 'Hello'}]
        
        response = dashscope.Generation.call(
            model=model_name,
            messages=messages,
            result_format='message',
        )
        
        if response.status_code == 200:
            print(f"✅ Success! Response: {response.output.choices[0].message.content}")
            return True
        else:
            print(f"❌ Failed. Code: {response.code}, Message: {response.message}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    # test_model("qwen-plus")
    test_model("qwen-max")
