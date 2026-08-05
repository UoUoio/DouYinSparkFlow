const { createApp, ref, reactive, computed } = Vue;
const app = createApp({
  setup() {
    const message = ref("Hello vue!");

    const match_mode_options = [
      {
        id: "nickname",
        label: "昵称",
        value: "nickname",
      },
      {
        id: "short_id",
        label: "抖音号",
        value: "short_id",
      },
    ];

    const log_level_options = [
      {
        id: "Debug",
        label: "Debug",
        value: "Debug",
      },
      {
        id: "Info",
        label: "Info",
        value: "Info",
      },
      {
        id: "Warning",
        label: "Warning",
        value: "Warning",
      },
      {
        id: "Error",
        label: "Error",
        value: "Error",
      },
    ];

    // do not use same name with ref
    const form = reactive({
      PROXY_ADDRESS: "",
      MESSAGE_TEMPLATE:
        "[盖瑞]今日火花[加一]\n—— [右边] 每日一言 [左边] ——\n[API]",
      HITOKOTO_TYPES: ["文学", "影视", "诗词", "哲学"],
      MATCH_MODE: "nickname",
      BROWSER_TIMEOUT: 120000,
      FRIEND_LIST_WAIT_TIME: 2000,
      TASK_RETRY_TIMES: 3,
      SEND_INTERVAL: 5,
      LOG_LEVEL: "Info",
      ACCOUNTS: [
        {
          username: "user1",
          unique_id: "12345678905",
          cookies: "cookie1",
          targets: ["friend1", "friend2"],
        },
      ],
    });

    // 把所有配置打包成一个 JSON 对象，对应后端的 CONFIG_JSON 环境变量：
    // GitHub 上只需要新增这一个 Secret，不用再逐条添加 Variables/Secrets，
    // 每个账号的 cookies 也直接内嵌在 TASKS 里，不用再单独配 COOKIES_<抖音号>
    const configBundle = computed(() => {
      return {
        PROXY_ADDRESS: form.PROXY_ADDRESS,
        MESSAGE_TEMPLATE: form.MESSAGE_TEMPLATE,
        HITOKOTO_TYPES: form.HITOKOTO_TYPES,
        MATCH_MODE: form.MATCH_MODE,
        BROWSER_TIMEOUT: form.BROWSER_TIMEOUT,
        FRIEND_LIST_WAIT_TIME: form.FRIEND_LIST_WAIT_TIME,
        TASK_RETRY_TIMES: form.TASK_RETRY_TIMES,
        SEND_INTERVAL: form.SEND_INTERVAL,
        LOG_LEVEL: form.LOG_LEVEL,
        TASKS: form.ACCOUNTS.map((account) => ({
          username: account.username,
          unique_id: account.unique_id,
          cookies: account.cookies,
          targets: account.targets,
        })),
      };
    });

    const configBundleJson = computed(() => JSON.stringify(configBundle.value));

    // 每个账户表单的必填校验规则：抖音号、Cookies、目标好友缺一不可，
    // 否则生成的配置会缺账号标识/登录凭证/发送对象，后端会直接跳过这个账户
    const accountRules = {
      unique_id: [
        { required: true, message: "必填：这个账号自己的抖音号", trigger: "blur" },
      ],
      cookies: [
        { required: true, message: "必填：粘贴 Cookies（JSON 格式）", trigger: "blur" },
      ],
      targets: [
        {
          required: true,
          type: "array",
          min: 1,
          message: "必填：至少添加一个目标好友",
          trigger: "change",
        },
      ],
    };

    // 收集每个账户表单的实例，用于按需触发校验
    const accountFormRefs = ref([]);
    const setAccountFormRef = (el, index) => {
      accountFormRefs.value[index] = el;
    };

    // 校验单个账户表单，校验不通过时把错误提示显示在对应字段下面
    const validateAccountForm = (index) => {
      const formRef = accountFormRefs.value[index];
      if (!formRef) return Promise.resolve(true);
      return formRef
        .validate()
        .then(() => true)
        .catch(() => false);
    };

    // 依次校验所有已添加的账户，任何一个不通过就提示具体是哪个账户、并中止后续操作
    const validateAllAccounts = async () => {
      for (let i = 0; i < form.ACCOUNTS.length; i++) {
        const ok = await validateAccountForm(i);
        if (!ok) {
          ElementPlus.ElMessage.warning(
            `请先完整填写"账户 ${i + 1}"的必填项（抖音号 / Cookies / 目标好友）`
          );
          return false;
        }
      }
      return true;
    };

    const copyValue = (value) => {
      if (typeof value === "object") {
        value = JSON.stringify(value);
      } else if (typeof value === "number") {
        value = value.toString();
      } else {
        value = value.replace(/\n/g, "\\n");
      }
      navigator.clipboard.writeText(value).then(
        () => {
          ElementPlus.ElMessage.success("已复制到剪贴板");
        },
        (err) => {
          ElementPlus.ElMessage.error("复制失败: " + err);
        }
      );
    };

    const toBase64 = (str) => {
      // 兼容 JSON 里的中文等非 Latin1 字符
      return btoa(unescape(encodeURIComponent(str)));
    };

    const copyEnvFile = async () => {
      if (!(await validateAllAccounts())) return;
      // .env 用 CONFIG_JSON_B64（base64 编码），而不是把原始 JSON 直接放进 .env：
      // .env 由 python-dotenv 按 KEY=VALUE 逐行解析，JSON 里常见的 # （比如消息模板/
      // 好友昵称里的 "#话题#"）会被当成行内注释截断，用引号包裹又可能被 JSON 内部出现
      // 的单引号破坏，所以统一转成 base64 规避这些解析边界问题
      const item = `CONFIG_JSON_B64=${toBase64(configBundleJson.value)}`;
      navigator.clipboard.writeText(item).then(
        () => {
          ElementPlus.ElMessage.success("已复制 .env 配置文件到剪贴板");
        },
        (err) => {
          ElementPlus.ElMessage.error("复制失败: " + err);
        }
      );
    };

    // "变量值"/"查看详情"按钮用的是 CONFIG_JSON 的实际内容，点之前先校验必填项，
    // 避免复制出一份缺账号信息的配置；"变量名"按钮复制的是固定字符串 "CONFIG_JSON"，
    // 跟账户数据无关，不需要校验
    const copyConfigValue = async () => {
      if (!(await validateAllAccounts())) return;
      copyValue(configBundleJson.value);
    };

    const showConfigDetails = async () => {
      if (!(await validateAllAccounts())) return;
      openEnvDetails("CONFIG_JSON", configBundle.value);
    };

    const openEnvDetails = (name, value) => {
      console.log(
        "openEnvDetails called with name:",
        name,
        "value:",
        value,
        typeof value
      );
      if (typeof value === "object") {
        value = JSON.stringify(value, null, 2);
        console.log("value is object, stringify it:", value);
      }

      ElementPlus.ElMessageBox.alert(
        "<div style='text-align: left; white-space: pre-wrap; word-break: break-all; width: 400px; max-height: 200px; overflow: auto;'>" +
          value +
          "</div>",
        `${name} 详情`,
        {
          dangerouslyUseHTMLString: true,
        }
      );
    };

    const addAccount = async () => {
      // 必须先把当前最后一个账户的必填项填完，才允许新增下一个账户
      const lastIndex = form.ACCOUNTS.length - 1;
      if (!(await validateAccountForm(lastIndex))) {
        ElementPlus.ElMessage.warning(
          `请先完整填写"账户 ${lastIndex + 1}"的必填项（抖音号 / Cookies / 目标好友），再添加下一个账户`
        );
        return;
      }
      form.ACCOUNTS.push({
        username: "",
        unique_id: "",
        cookies: "",
        targets: [],
      });
    };

    const removeAccount = (index) => {
      form.ACCOUNTS.splice(index, 1);
      accountFormRefs.value.splice(index, 1);
    };

    return {
      match_mode_options,
      log_level_options,
      message,
      form,
      accountRules,
      setAccountFormRef,
      configBundle,
      configBundleJson,
      copyValue,
      copyConfigValue,
      showConfigDetails,
      copyEnvFile,
      openEnvDetails,
      addAccount,
      removeAccount,
    };
  },
});
app.use(ElementPlus);
app.mount("#app");
