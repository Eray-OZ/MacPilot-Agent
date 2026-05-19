package com.example.macremote

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.POST
import java.util.UUID
import java.util.concurrent.TimeUnit

// ==========================================
// 1. DATA MODELS & NETWORK INTERFACE
// ==========================================

data class CommandRequest(val command: String)

data class AgentResponse(val response: String, val status: String)

data class HistoryItem(
    val id: String = UUID.randomUUID().toString(),
    val command: String,
    val response: String,
    val isSuccess: Boolean,
    val timestamp: Long = System.currentTimeMillis()
)

interface ApiService {
    @POST("run-agent")
    suspend fun runAgent(@Body request: CommandRequest): AgentResponse
}

// Retrofit Client - Dynamic IP Address config support
object RetrofitClient {
    private var currentIp: String? = null
    private var apiService: ApiService? = null

    fun getService(ip: String): ApiService {
        val sanitizedIp = ip.trim()
            .removePrefix("http://")
            .removePrefix("https://")
            .removeSuffix("/")
        val baseUrl = if (sanitizedIp.contains(":")) {
            "http://$sanitizedIp/"
        } else {
            "http://$sanitizedIp:8000/"
        }

        if (currentIp != sanitizedIp || apiService == null) {
            currentIp = sanitizedIp
            val okHttpClient = OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .build()

            val retrofit = Retrofit.Builder()
                .baseUrl(baseUrl)
                .client(okHttpClient)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
            apiService = retrofit.create(ApiService::class.java)
        }
        return apiService!!
    }
}

// ==========================================
// 2. VIEWMODEL FOR STATE MANAGEMENT
// ==========================================

sealed interface UiState {
    object Idle : UiState
    object Loading : UiState
    data class Success(val message: String) : UiState
    data class Error(val error: String) : UiState
}

class RemoteControlViewModel : ViewModel() {
    private val _ipAddress = MutableStateFlow("192.168.1.100") // Default local IP
    val ipAddress: StateFlow<String> = _ipAddress.asStateFlow()

    private val _commandText = MutableStateFlow("")
    val commandText: StateFlow<String> = _commandText.asStateFlow()

    private val _uiState = MutableStateFlow<UiState>(UiState.Idle)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    private val _history = MutableStateFlow<List<HistoryItem>>(emptyList())
    val history: StateFlow<List<HistoryItem>> = _history.asStateFlow()

    fun updateIpAddress(newIp: String) {
        _ipAddress.value = newIp
    }

    fun updateCommandText(newCommand: String) {
        _commandText.value = newCommand
    }

    fun sendCommand() {
        val command = _commandText.value.trim()
        val ip = _ipAddress.value.trim()

        if (command.isEmpty()) return

        _uiState.value = UiState.Loading
        _commandText.value = "" // Clear input field

        viewModelScope.launch {
            try {
                val apiService = RetrofitClient.getService(ip)
                val response = apiService.runAgent(CommandRequest(command))
                
                val isSuccess = response.status == "success"
                
                _uiState.value = if (isSuccess) {
                    UiState.Success(response.response)
                } else {
                    UiState.Error(response.response)
                }

                // Add to history list
                _history.value = listOf(
                    HistoryItem(
                        command = command,
                        response = response.response,
                        isSuccess = isSuccess
                    )
                ) + _history.value

            } catch (e: Exception) {
                val errorMsg = "Connection Error: Please check the Mac IP address and ensure the server is running. (Details: ${e.localizedMessage})"
                _uiState.value = UiState.Error(errorMsg)
                
                _history.value = listOf(
                    HistoryItem(
                        command = command,
                        response = errorMsg,
                        isSuccess = false
                    )
                ) + _history.value
            }
        }
    }
}

// ==========================================
// 3. UI COMPONENTS & JETPACK COMPOSE
// ==========================================

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(
                colorScheme = darkColorScheme(
                    primary = Color(0xFF6C63FF),
                    onPrimary = Color.White,
                    secondary = Color(0xFF03DAC5),
                    background = Color(0xFF121212),
                    surface = Color(0xFF1E1E1E),
                    error = Color(0xFFCF6679)
                )
            ) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    RemoteControlScreen()
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RemoteControlScreen(viewModel: RemoteControlViewModel = viewModel()) {
    val ipAddress by viewModel.ipAddress.collectAsState()
    val commandText by viewModel.commandText.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    val history by viewModel.history.collectAsState()
    
    var showSettings by remember { mutableStateOf(false) }
    val keyboardController = LocalSoftwareKeyboardController.current
    val listState = rememberLazyListState()

    // Smooth scroll to top whenever a new command is added
    LaunchedEffect(history.size) {
        if (history.isNotEmpty()) {
            listState.animateScrollToItem(0)
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = "Mac Remote Control",
                            fontWeight = FontWeight.Bold,
                            fontSize = 20.sp,
                            color = Color.White
                        )
                        Text(
                            text = "Server: $ipAddress:8000",
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.secondary
                        )
                    }
                },
                actions = {
                    IconButton(onClick = { showSettings = !showSettings }) {
                        Icon(
                            imageVector = Icons.Default.Settings,
                            contentDescription = "Connection Settings",
                            tint = Color.White
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .background(MaterialTheme.colorScheme.background)
        ) {
            // Settings (Dynamic IP Config Area)
            AnimatedVisibility(
                visible = showSettings,
                enter = expandVertically() + fadeIn(),
                exit = shrinkVertically() + fadeOut()
            ) {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    shape = RoundedCornerShape(16.dp),
                    elevation = CardDefaults.cardElevation(defaultElevation = 4.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text = "Connection Settings",
                            fontWeight = FontWeight.Bold,
                            fontSize = 16.sp,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.padding(bottom = 8.dp)
                        )
                        OutlinedTextField(
                            value = ipAddress,
                            onValueChange = { viewModel.updateIpAddress(it) },
                            label = { Text("Mac Local IP Address") },
                            placeholder = { Text("e.g., 192.168.1.100") },
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(
                                keyboardType = KeyboardType.Number,
                                imeAction = ImeAction.Done
                            ),
                            keyboardActions = KeyboardActions(
                                onDone = { showSettings = false }
                            ),
                            modifier = Modifier.fillMaxWidth(),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = MaterialTheme.colorScheme.primary,
                                unfocusedBorderColor = Color.Gray
                            )
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "Note: Your phone and Mac must be connected to the same Wi-Fi network.",
                            fontSize = 11.sp,
                            color = Color.LightGray
                        )
                    }
                }
            }

            // Status Indicator (Loading or Result Notification)
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp)
            ) {
                AnimatedContent(targetState = uiState, label = "StateAnimation") { state ->
                    when (state) {
                        is UiState.Loading -> {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(MaterialTheme.colorScheme.surface)
                                    .padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.Center
                            ) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(24.dp),
                                    color = MaterialTheme.colorScheme.primary,
                                    strokeWidth = 3.dp
                                )
                                Spacer(modifier = Modifier.width(12.dp))
                                Text(
                                    text = "Mac is processing the command, please wait...",
                                    fontSize = 14.sp,
                                    fontWeight = FontWeight.Medium
                                )
                            }
                        }
                        is UiState.Success -> {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(Color(0xFF1E3A2F))
                                    .padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(
                                    imageVector = Icons.Default.CheckCircle,
                                    contentDescription = "Success",
                                    tint = Color(0xFF4CAF50)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    text = state.message,
                                    color = Color(0xFFE8F5E9),
                                    fontSize = 14.sp
                                )
                            }
                        }
                        is UiState.Error -> {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(Color(0xFF3E1F24))
                                    .padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Warning,
                                    contentDescription = "Error",
                                    tint = MaterialTheme.colorScheme.error
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    text = state.error,
                                    color = Color(0xFFFFEBEE),
                                    fontSize = 14.sp
                                )
                            }
                        }
                        is UiState.Idle -> {
                            // Initial state can remain blank
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Command History and Chat List
            LazyColumn(
                modifier = Modifier
                    .weight(1.0f)
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
                state = listState,
                verticalArrangement = Arrangement.spacedBy(12.dp),
                contentPadding = PaddingValues(bottom = 16.dp, top = 8.dp)
            ) {
                if (history.isEmpty()) {
                    item {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 60.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Icon(
                                    imageVector = Icons.Default.Info,
                                    contentDescription = "Hint",
                                    tint = Color.Gray,
                                    modifier = Modifier.size(48.dp)
                                )
                                Spacer(modifier = Modifier.height(12.dp))
                                Text(
                                    text = "No commands sent yet.",
                                    color = Color.Gray,
                                    fontSize = 15.sp
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = "e.g., 'open Spotify' or 'close Chrome'",
                                    color = Color.DarkGray,
                                    fontSize = 13.sp
                                )
                            }
                        }
                    }
                } else {
                    items(history, key = { it.id }) { item ->
                        HistoryBubbleItem(item)
                    }
                }
            }

            // Bottom Command Input Field
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(MaterialTheme.colorScheme.surface)
                    .padding(16.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedTextField(
                        value = commandText,
                        onValueChange = { viewModel.updateCommandText(it) },
                        placeholder = { Text("Type a command for your Mac...") },
                        modifier = Modifier
                            .weight(1.0f)
                            .padding(end = 8.dp),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(
                            imeAction = ImeAction.Send
                        ),
                        keyboardActions = KeyboardActions(
                            onSend = {
                                if (commandText.isNotBlank()) {
                                    viewModel.sendCommand()
                                    keyboardController?.hide()
                                }
                            }
                        ),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = MaterialTheme.colorScheme.primary,
                            unfocusedBorderColor = Color.DarkGray,
                            focusedContainerColor = MaterialTheme.colorScheme.background,
                            unfocusedContainerColor = MaterialTheme.colorScheme.background
                        ),
                        shape = RoundedCornerShape(24.dp)
                    )

                    FloatingActionButton(
                        onClick = {
                            if (commandText.isNotBlank()) {
                                viewModel.sendCommand()
                                keyboardController?.hide()
                            }
                        },
                        containerColor = if (commandText.isNotBlank()) MaterialTheme.colorScheme.primary else Color.DarkGray,
                        contentColor = Color.White,
                        shape = RoundedCornerShape(50),
                        modifier = Modifier.size(50.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Send,
                            contentDescription = "Send"
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun HistoryBubbleItem(item: HistoryItem) {
    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.End
    ) {
        // User Command (Right Side)
        Box(
            modifier = Modifier
                .align(Alignment.End)
                .padding(start = 40.dp)
                .clip(RoundedCornerShape(16.dp, 16.dp, 0.dp, 16.dp))
                .background(
                    Brush.horizontalGradient(
                        colors = listOf(Color(0xFF8E2DE2), Color(0xFF4A00E0))
                    )
                )
                .padding(horizontal = 16.dp, vertical = 10.dp)
        ) {
            Text(
                text = item.command,
                color = Color.White,
                fontSize = 15.sp,
                fontWeight = FontWeight.Medium
            )
        }

        Spacer(modifier = Modifier.height(6.dp))

        // Mac/Agent Response (Left Side)
        Box(
            modifier = Modifier
                .align(Alignment.Start)
                .padding(end = 40.dp)
                .clip(RoundedCornerShape(16.dp, 16.dp, 16.dp, 0.dp))
                .background(
                    if (item.isSuccess) Color(0xFF2C2C2C) else Color(0xFF422226)
                )
                .padding(horizontal = 16.dp, vertical = 10.dp)
        ) {
            Text(
                text = item.response,
                color = if (item.isSuccess) Color.LightGray else Color(0xFFFFCDD2),
                fontSize = 14.sp
            )
        }
    }
}
