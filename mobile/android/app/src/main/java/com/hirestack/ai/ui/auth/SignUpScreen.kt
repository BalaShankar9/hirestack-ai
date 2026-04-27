package com.hirestack.ai.ui.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.focus.focusRequester
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material.icons.outlined.Email
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.HireStackPrimaryButton
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.PillTone

@Composable
fun SignUpScreen(
    vm: AuthViewModel,
    onAuthenticated: () -> Unit,
    onLoginClick: () -> Unit,
) {
    val state by vm.state.collectAsState()
    val toastCtx = androidx.compose.ui.platform.LocalContext.current
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var fullName by remember { mutableStateOf("") }
    var passwordVisible by remember { mutableStateOf(false) }
    val keyboardController = androidx.compose.ui.platform.LocalSoftwareKeyboardController.current
    val nameFocus = remember { androidx.compose.ui.focus.FocusRequester() }
    val signUpFocusManager = androidx.compose.ui.platform.LocalFocusManager.current
    androidx.compose.runtime.LaunchedEffect(Unit) { runCatching { nameFocus.requestFocus() } }

    Scaffold(containerColor = Color.Transparent) { padding ->
        BrandBackground {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .imePadding()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 28.dp, vertical = 32.dp),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                BrandLogo()
                Spacer(Modifier.height(20.dp))
                Text(
                    "Create your account",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    "Free to start. Land interviews faster.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(28.dp))

                OutlinedTextField(
                    value = fullName,
                    onValueChange = { fullName = it; vm.clearError() },
                    label = { Text("Full name (optional)") },
                    leadingIcon = { Icon(Icons.Outlined.Person, null) },
                    singleLine = true,
                    shape = RoundedCornerShape(14.dp),
                    keyboardOptions = KeyboardOptions(imeAction = androidx.compose.ui.text.input.ImeAction.Next),
                    keyboardActions = androidx.compose.foundation.text.KeyboardActions(onNext = { signUpFocusManager.moveFocus(androidx.compose.ui.focus.FocusDirection.Down) }),
                    modifier = Modifier.fillMaxWidth().focusRequester(nameFocus),
                )
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it; vm.clearError() },
                    label = { Text("Email") },
                    leadingIcon = { Icon(Icons.Outlined.Email, null) },
                    singleLine = true,
                    shape = RoundedCornerShape(14.dp),
                    isError = email.isNotEmpty() && !android.util.Patterns.EMAIL_ADDRESS.matcher(email.trim()).matches(),
                    supportingText = {
                        if (email.isNotEmpty() && !android.util.Patterns.EMAIL_ADDRESS.matcher(email.trim()).matches()) {
                            Text("Enter a valid email address")
                        }
                    },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = androidx.compose.ui.text.input.ImeAction.Next),
                    keyboardActions = androidx.compose.foundation.text.KeyboardActions(onNext = { signUpFocusManager.moveFocus(androidx.compose.ui.focus.FocusDirection.Down) }),
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it; vm.clearError() },
                    label = { Text("Password (min 6)") },
                    leadingIcon = { Icon(Icons.Outlined.Lock, null) },
                    trailingIcon = {
                        IconButton(onClick = { passwordVisible = !passwordVisible }) {
                            Icon(
                                if (passwordVisible) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                                contentDescription = if (passwordVisible) "Hide password" else "Show password",
                            )
                        }
                    },
                    singleLine = true,
                    shape = RoundedCornerShape(14.dp),
                    visualTransformation = if (passwordVisible) VisualTransformation.None else PasswordVisualTransformation(),
                    isError = password.isNotEmpty() && password.length < 6,
                    supportingText = {
                        if (password.isNotEmpty() && password.length < 6) {
                            Text("At least 6 characters")
                        }
                    },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = androidx.compose.ui.text.input.ImeAction.Done),
                    keyboardActions = androidx.compose.foundation.text.KeyboardActions(onDone = {
                        keyboardController?.hide()
                        val e = email.trim()
                        if (!state.isLoading && android.util.Patterns.EMAIL_ADDRESS.matcher(e).matches() && password.length >= 6) {
                            vm.clearError()
                            vm.signUp(e, password, fullName.takeIf { it.isNotBlank() }) { ok ->
                                if (ok) { android.widget.Toast.makeText(toastCtx, "Account created", android.widget.Toast.LENGTH_SHORT).show(); onAuthenticated() }
                            }
                        }
                    }),
                    modifier = Modifier.fillMaxWidth(),
                )

                state.error?.let {
                    Spacer(Modifier.height(12.dp))
                    InlineBanner(it, tone = PillTone.Danger)
                }

                Spacer(Modifier.height(20.dp))
                HireStackPrimaryButton(
                    label = if (state.isLoading) "Creating account…" else "Create account",
                    onClick = {
                        vm.clearError()
                        vm.signUp(email.trim(), password, fullName.takeIf { it.isNotBlank() }) { ok ->
                            if (ok) { android.widget.Toast.makeText(toastCtx, "Account created", android.widget.Toast.LENGTH_SHORT).show(); onAuthenticated() }
                        }
                    },
                    enabled = !state.isLoading && android.util.Patterns.EMAIL_ADDRESS.matcher(email.trim()).matches() && password.length >= 6,
                    modifier = Modifier.fillMaxWidth(),
                )
                if (state.isLoading) {
                    Spacer(Modifier.height(8.dp))
                    CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                }

                Spacer(Modifier.height(8.dp))
                TextButton(onClick = onLoginClick) {
                    Text("Already have an account? Sign in")
                }
            }
        }
    }
}
