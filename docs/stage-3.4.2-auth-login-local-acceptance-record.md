# Stage 3.4.2 Auth Login Local Acceptance Record

## Stage Conclusion

Stage 3.4.2 records the local browser acceptance result for the Stage 3.4.1
auth login gate. The local browser acceptance passed.

This stage is an acceptance-record stage only. It does not change authentication
logic, does not perform cutover, and does not change the production network
link state.

## Acceptance Environment

- Frontend URL: `http://localhost:3000`
- Acceptance type: local browser acceptance
- Real password handling: entered only in the browser by the operator

## Acceptance Results

| Item | Result | Notes |
| --- | --- | --- |
| Unauthenticated visit shows only the login page | Passed | Backend panels were not visible before login. |
| Wrong username or password shows login failure | Passed | Login failure message was displayed. |
| Correct username and password enters the system panel | Passed | Existing system panel opened after successful login. |
| Refresh keeps the logged-in session | Passed | Session remained active after page refresh. |
| Logout returns to the login page | Passed | Logout completed and the login page returned. |
| System panel is hidden after logout | Passed | Backend management panels were no longer visible after logout. |

## Security Notes

- The real password was entered only in the browser.
- The real password was not written to this document.
- The real password was not written to terminal commands.
- The real password was not written to logs.
- The real password was not written to Git.

## API Protection Notes

Stage 3.4.1 already recorded the basic protected API behavior:
unauthenticated requests to protected APIs return `401`.

Stage 3.4.2 records the final browser-side acceptance for the login gate:
login page visibility, failed login feedback, successful login, session
persistence after refresh, logout, and post-logout panel hiding.

## Production Link Boundary

- The formal production link remains `socat` 18443.
- The fallback link remains `gost` 8443.
- `node.share_link` was not read, printed, or modified in this stage.
- No network cutover action was performed.

## Safety Boundary

- No real password was written.
- No SSH Key was written.
- No Passphrase was written.
- No token was written.
- No full node link was written.
- `node.share_link` was not read or modified.
- No database migration was added.
- No listening port was added.
- No SSH or remote command was executed.
- No backend task was triggered.
- No firewall rule was modified.
- `socat` did not take over 8443.
- `gost` 8443 was not closed, stopped, disabled, downgraded, or replaced.
- No cutover was performed.

## Stage Result

Stage 3.4.2 confirms that the Stage 3.4.1 login gate passed local browser
acceptance. The current production link state remains unchanged:
`socat` 18443 is the formal link and `gost` 8443 is retained as the fallback
link.
