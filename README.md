
</div>

<div align="center">

![:name](https://count.getloli.com/@InitiativeDialogue?name=InitiativeDialogue&theme=minecraft&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

</div>

# 插件介绍
 
astrbot_plugin_InitiativeDialogue是一款能让bot主动发起对话的插件

在私聊时，当用户长时间未与bot进行对话，则会触发此插件使bot主动发起对话
 
# 主要功能介绍
  
该插件会自动侦测bot列表中的所有私聊会话，并记录每个会话用户发送的最后一条消息的时间以及会话id.
 
当达到指定未回复时间时（默认为2h），若用户未对bot发起对话，则会创建主动对话任务，在设定回复时间内（默认为1h）随机时间点发起对话。
 
发起对话的原理是先从prompts库中随机挑选一条，结合用户的人格设定prompt一并发送给llm，获取到llm返回的文本后发送给相应的会话，并清除任务。
 
所有时间节点以及prompts库均可根据用户的喜好进行变更，可在配置文件中对这些参数进行修改。

# 更新
 
1.现已加入白名单，让bot只对指定用户发起主动对话。

2.使用了llm钩子，使bot能对用户的回应作出更生动的回答。


 
